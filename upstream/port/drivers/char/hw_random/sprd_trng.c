// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc UMS9620 (qogirn6pro) true random number generator: the TRNG of the public crypto engine (rng@e0000,
 * "sprd,sprd-trng"), which gives /dev/hwrng and feeds the kernel's random pool.
 *
 * Ported from the Unisoc 5.4 kernel (drivers/char/hw_random/sprd_trng.c, Guozhu Xing <guozhu.xing@unisoc.com>):
 * the same registers, clocks and enable sequence. What changed for mainline: the read never writes past the
 * caller's buffer (the vendor code rounded up to whole words), it waits for data with a bounded poll instead of
 * logging every empty status read, and the clocks are held from the hwrng core's init to its cleanup rather than switched by runtime PM.
 */
#include <linux/clk.h>
#include <linux/err.h>
#include <linux/hw_random.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mod_devicetable.h>
#include <linux/platform_device.h>
#include <linux/pm.h>
#include <linux/string.h>

#define REG_CE_CLK		0x018
#define REG_CE_RNG_EN		0x200
#define REG_CE_RNG_DATA		0x208
#define REG_CE_RNG_WORK_STATUS	0x214
#define REG_CE_RNG_MODE		0x228

#define TRNG_CLK_EN		BIT(24)
#define RNG_ENABLE		0x1ff03
#define RNG_DATA_VALID		BIT(1)
#define TRNG_MODE		BIT(0)

/* one burst: the vendor driver's RNG_DATABUF_SIZE */
#define TRNG_BURST		32
/* the vendor driver gave the engine ten 1 ms tries */
#define TRNG_TIMEOUT_US		10000

struct sprd_trng {
	void __iomem *base;
	struct hwrng rng;
	struct clk *clk;
	struct clk *ce_eb;
	struct device *dev;
	bool on;
};

#define to_sprd_trng(p) container_of(p, struct sprd_trng, rng)

static void sprd_trng_update(struct sprd_trng *trng, u32 reg, u32 mask, u32 val)
{
	u32 v = readl_relaxed(trng->base + reg);

	writel_relaxed((v & ~mask) | val, trng->base + reg);
}

static void sprd_trng_start(struct sprd_trng *trng)
{
	sprd_trng_update(trng, REG_CE_CLK, TRNG_CLK_EN, TRNG_CLK_EN);
	sprd_trng_update(trng, REG_CE_RNG_EN, RNG_ENABLE, RNG_ENABLE);
	sprd_trng_update(trng, REG_CE_RNG_MODE, TRNG_MODE, TRNG_MODE);
}

static int sprd_trng_init(struct hwrng *rng)
{
	struct sprd_trng *trng = to_sprd_trng(rng);
	int ret;

	ret = clk_prepare_enable(trng->clk);
	if (ret)
		return ret;
	ret = clk_prepare_enable(trng->ce_eb);
	if (ret) {
		clk_disable_unprepare(trng->clk);
		return ret;
	}
	sprd_trng_start(trng);
	trng->on = true;
	return 0;
}

static void sprd_trng_cleanup(struct hwrng *rng)
{
	struct sprd_trng *trng = to_sprd_trng(rng);

	trng->on = false;
	sprd_trng_update(trng, REG_CE_RNG_EN, RNG_ENABLE, 0);
	sprd_trng_update(trng, REG_CE_CLK, TRNG_CLK_EN, 0);
	clk_disable_unprepare(trng->ce_eb);
	clk_disable_unprepare(trng->clk);
}

static int sprd_trng_read(struct hwrng *rng, void *buf, size_t max, bool wait)
{
	struct sprd_trng *trng = to_sprd_trng(rng);
	size_t got = 0;
	u32 status, w;

	max = min_t(size_t, max, TRNG_BURST);
	if (!max)
		return 0;
	if (wait) {
		if (readl_relaxed_poll_timeout(trng->base + REG_CE_RNG_WORK_STATUS, status,
					       status & RNG_DATA_VALID, 100, TRNG_TIMEOUT_US)) {
			dev_dbg(trng->dev, "no random data\n");
			return 0;
		}
	} else if (!(readl_relaxed(trng->base + REG_CE_RNG_WORK_STATUS) & RNG_DATA_VALID)) {
		return 0;
	}
	while (got < max) {
		w = readl_relaxed(trng->base + REG_CE_RNG_DATA);
		memcpy(buf + got, &w, min_t(size_t, sizeof(w), max - got));
		got += min_t(size_t, sizeof(w), max - got);
	}
	return got;
}

static int sprd_trng_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct sprd_trng *trng;
	struct clk *parent;
	int ret;

	trng = devm_kzalloc(dev, sizeof(*trng), GFP_KERNEL);
	if (!trng)
		return -ENOMEM;
	trng->dev = dev;
	trng->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(trng->base))
		return PTR_ERR(trng->base);
	trng->clk = devm_clk_get(dev, "ap-ce-clk");
	if (IS_ERR(trng->clk))
		return dev_err_probe(dev, PTR_ERR(trng->clk), "no ap-ce-clk\n");
	trng->ce_eb = devm_clk_get(dev, "ce-pub-eb");
	if (IS_ERR(trng->ce_eb))
		return dev_err_probe(dev, PTR_ERR(trng->ce_eb), "no ce-pub-eb\n");
	parent = devm_clk_get(dev, "source");
	if (IS_ERR(parent))
		return dev_err_probe(dev, PTR_ERR(parent), "no source clock\n");
	ret = clk_set_parent(trng->clk, parent);
	if (ret)
		dev_warn(dev, "cannot set the CE clock's parent: %d\n", ret);

	/* the 5.4 driver's name: /sys/class/misc/hw_random/rng_available shows 202e0000.rng as it did there */
	trng->rng.name = dev_name(dev);
	trng->rng.init = sprd_trng_init;
	trng->rng.cleanup = sprd_trng_cleanup;
	trng->rng.read = sprd_trng_read;
	platform_set_drvdata(pdev, trng);

	ret = devm_hwrng_register(dev, &trng->rng);
	if (ret)
		return dev_err_probe(dev, ret, "cannot register the hwrng\n");
	return 0;
}

/* the clocks stay as the hwrng core left them; what the engine may have lost over a system sleep is set again */
static int sprd_trng_resume(struct device *dev)
{
	struct sprd_trng *trng = dev_get_drvdata(dev);

	if (trng->on)
		sprd_trng_start(trng);
	return 0;
}

static DEFINE_SIMPLE_DEV_PM_OPS(sprd_trng_pm_ops, NULL, sprd_trng_resume);

static const struct of_device_id sprd_trng_of_match[] = {
	{ .compatible = "sprd,sprd-trng" },
	{ }
};
MODULE_DEVICE_TABLE(of, sprd_trng_of_match);

static struct platform_driver sprd_trng_driver = {
	.probe = sprd_trng_probe,
	.driver = {
		.name = "sprd_trng",
		.pm = pm_sleep_ptr(&sprd_trng_pm_ops),
		.of_match_table = sprd_trng_of_match,
	},
};
module_platform_driver(sprd_trng_driver);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unisoc UMS9620 true random number generator");
