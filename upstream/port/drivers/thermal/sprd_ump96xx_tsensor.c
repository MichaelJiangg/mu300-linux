// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc UMP9622 temperature sensors (tsensor@20f8 on pmic@2): the crystal oscillator's sensor (osc-tsensor@0,
 * the osctsen-thmzone) and the PMIC's own (tout-tsensor@1, the outtsen-thmzone).
 *
 * Ported from the Unisoc 5.4 kernel (drivers/thermal/sprd_ump96xx_tsensor.c), and it behaves as that driver does:
 * the sensors are read only when the bootloader starts the factory calibration mode (androidboot.mode=cali on the
 * command line it passes in /chosen/bootargs); in any other boot the driver leaves the sensor block alone. The
 * oscillator's sensor sits next to the 26 MHz crystal the modem's clock comes from, and the sequence that reads it
 * switches the sensor block's clock, channel and enables, so outside calibration nothing on the AP touches it.
 * What differs: on 5.4 the device tree's thermal zones existed whether or not a sensor was registered; mainline
 * creates a zone only for a registered sensor, so both are registered in every boot, and outside calibration
 * mode a read of their temperature fails with EAGAIN (no value), as a 5.4 zone without its sensor did.
 */
#include <linux/delay.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/string.h>
#include <linux/thermal.h>

#define UMP96XX_XTL_WAIT_CTRL0		0x20e0
#define UMP96XX_XTL_EN			BIT(8)

#define UMP96XX_TSEN_CTRL0		0x0
#define UMP96XX_TSEN_CLK_SRC_SEL	BIT(4)
#define UMP96XX_TSEN_CTRL1		0x4
#define UMP96XX_TSEN_26M_EN		BIT(0)
#define UMP96XX_TSEN_SDADC_EN		BIT(4)
#define UMP96XX_TSEN_CTRL3		0xc
#define UMP96XX_TSEN_SEL_CH		BIT(3)
#define UMP96XX_TSEN_EN			BIT(4)
#define UMP96XX_TSEN_UGBUF_EN		BIT(8)
#define UMP96XX_TSEN_ADCLDO_EN		BIT(12)
#define UMP96XX_TSEN_CTRL4		0x10
#define UMP96XX_TSEN_CTRL5		0x14
#define UMP96XX_TSEN_CTRL6		0x18
#define UMP96XX_TSEN_SEL_EN		(BIT(6) | BIT(7))

#define UMP96XX_TSEN_OSC_TEMP(h, l) \
	(((((h & GENMASK(5, 3)) << 16) | (l & GENMASK(15, 0))) << 4) & 0xFFFFF)
#define UMP96XX_TSEN_TSEN_TEMP(h, l) \
	(((((h & GENMASK(2, 0)) << 16) | (l & GENMASK(15, 0))) << 4) & 0xFFFFF)

#define UMP96XX_TSEN_INDEX_MASK		GENMASK(7, 0)
#define UMP96XX_TSEN_INDEX_SHIFT	12
#define UMP96XX_TSEN_FRAC_MASK		GENMASK(11, 0)

/* temperature by the integral index (the vendor's table) */
static const int v2t_table[256] = {
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119,
	298119, 298119, 298119, 298119, 298119, 298119, 298119, 298119, 280421, 264933, 251238, 238928, 227748, 217492, 208038, 199268,
	191078, 183383, 176104, 169240, 162710, 156500, 150570, 144893, 139428, 134191, 129138, 124253, 119525, 114943, 110500, 106187,
	101990, 97905, 93919, 90026, 86224, 82506, 78860, 75286, 71777, 68330, 64940, 61606, 58337, 55113, 51932, 48790,
	45696, 42642, 39620, 36627, 33675, 30750, 27848, 24974, 22128, 19300, 16490, 13707, 10937, 8180, 5444, 2717,
	0, -2702, -5398, -8088, -10768, -13446, -16120, -18791, -21462, -24132, -26805, -29481, -32160, -34847, -37539, -40241,
	-42956, -45680, -48419, -51175, -53944, -56734, -59548, -62379, -65234, -68124, -71039, -73979, -76964, -79985, -83041, -86136,
	-89290, -92493, -95747, -99057, -102428, -105886, -109418, -113031, -116733, -120533, -124438, -128458, -132609, -136903, -141357,
	-145991, -150823, -155881, -161216, -166830, -172781, -179140, -185969, -193354, -201441, -210423, -220528, -232181, -245984,
	-263191, -263191, -263191,
};

static DEFINE_MUTEX(tsen_mutex);

struct ump96xx_tsen {
	struct regmap *regmap;
	u32 base;
	u32 id;
	bool cali_mode;
};

static int ump96xx_tsensor_read_config(struct ump96xx_tsen *tsen)
{
	static const struct { u32 reg; u32 bits; } seq[] = {
		{ UMP96XX_TSEN_CTRL0, UMP96XX_TSEN_CLK_SRC_SEL },
		{ UMP96XX_TSEN_CTRL1, UMP96XX_TSEN_26M_EN },
		{ UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_ADCLDO_EN },
		{ UMP96XX_TSEN_CTRL1, UMP96XX_TSEN_SDADC_EN },
		{ UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_UGBUF_EN },
		{ UMP96XX_TSEN_CTRL6, UMP96XX_TSEN_SEL_EN },
	};
	int i, ret;

	ret = regmap_update_bits(tsen->regmap, UMP96XX_XTL_WAIT_CTRL0, UMP96XX_XTL_EN, UMP96XX_XTL_EN);
	for (i = 0; !ret && i < ARRAY_SIZE(seq); i++)
		ret = regmap_update_bits(tsen->regmap, tsen->base + seq[i].reg, seq[i].bits, seq[i].bits);
	return ret;
}

/* one sample of channel osc (true) or out (false): the low word from lo_reg, the high bits from CTRL6 */
static int ump96xx_tsensor_sample(struct ump96xx_tsen *tsen, bool osc, u32 lo_reg, u32 *th, u32 *tl)
{
	int ret;

	ret = ump96xx_tsensor_read_config(tsen);
	if (!ret)
		ret = regmap_update_bits(tsen->regmap, tsen->base + UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_SEL_CH,
					 osc ? UMP96XX_TSEN_SEL_CH : 0);
	if (!ret)
		ret = regmap_update_bits(tsen->regmap, tsen->base + UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_EN,
					 UMP96XX_TSEN_EN);
	if (ret)
		return ret;
	/* the design document: a sample is ready 21 ms after the trigger */
	msleep(21);
	ret = regmap_read(tsen->regmap, tsen->base + lo_reg, tl);
	if (!ret)
		ret = regmap_read(tsen->regmap, tsen->base + UMP96XX_TSEN_CTRL6, th);
	return ret;
}

static int ump96xx_tsensor_get_temp(struct thermal_zone_device *tz, int *temp)
{
	struct ump96xx_tsen *tsen = thermal_zone_device_priv(tz);
	u32 th, tl, raw;
	int ret, index, frac, t;

	/* as on 5.4: nothing is read outside the factory calibration mode */
	if (!tsen->cali_mode)
		return -EAGAIN;

	mutex_lock(&tsen_mutex);
	if (tsen->id == 0)
		ret = ump96xx_tsensor_sample(tsen, true, UMP96XX_TSEN_CTRL5, &th, &tl);
	else
		ret = ump96xx_tsensor_sample(tsen, false, UMP96XX_TSEN_CTRL4, &th, &tl);
	mutex_unlock(&tsen_mutex);
	if (ret)
		return ret;

	if (tsen->id == 0) {
		raw = UMP96XX_TSEN_OSC_TEMP(th, tl);
		/* osc temp = 3641500 - (4856 * rawdata) / 1000 */
		*temp = 3641500 - (((4856 * (raw >> 4)) / 1000) << 4);
		return 0;
	}
	raw = UMP96XX_TSEN_TSEN_TEMP(th, tl);
	index = (raw >> UMP96XX_TSEN_INDEX_SHIFT) & UMP96XX_TSEN_INDEX_MASK;
	frac = raw & UMP96XX_TSEN_FRAC_MASK;
	if (index != ARRAY_SIZE(v2t_table) - 1)
		t = (v2t_table[index] * (0x1000 - frac) + v2t_table[index + 1] * frac + 0x800) / 4096;
	else
		t = v2t_table[index];
	/* out temp = (t * 1000) / 4096 + 25000 */
	*temp = (t * 1000) / 4096 + 25000;
	return 0;
}

static const struct thermal_zone_device_ops ump96xx_tsensor_ops = {
	.get_temp = ump96xx_tsensor_get_temp,
};

static int ump96xx_tsensor_disable(struct regmap *regmap, u32 base)
{
	static const struct { u32 reg; u32 bits; } seq[] = {
		{ UMP96XX_TSEN_CTRL0, UMP96XX_TSEN_CLK_SRC_SEL },
		{ UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_EN | UMP96XX_TSEN_SEL_CH },
		{ UMP96XX_TSEN_CTRL6, UMP96XX_TSEN_SEL_EN },
		{ UMP96XX_TSEN_CTRL1, UMP96XX_TSEN_SDADC_EN },
		{ UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_UGBUF_EN },
		{ UMP96XX_TSEN_CTRL3, UMP96XX_TSEN_ADCLDO_EN },
	};
	int i, ret = 0;

	for (i = 0; !ret && i < ARRAY_SIZE(seq); i++)
		ret = regmap_update_bits(regmap, base + seq[i].reg, seq[i].bits, 0);
	return ret;
}

static bool ump96xx_cali_mode(void)
{
	struct device_node *chosen = of_find_node_by_path("/chosen");
	const char *cmdline;
	bool cali = false;

	if (chosen && !of_property_read_string(chosen, "bootargs", &cmdline))
		cali = strstr(cmdline, "androidboot.mode=cali");
	of_node_put(chosen);
	return cali;
}

static int ump96xx_tsen_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct thermal_zone_device *tz;
	struct ump96xx_tsen *tsen;
	struct regmap *regmap;
	bool cali = ump96xx_cali_mode();
	u32 base;
	int ret;

	regmap = dev_get_regmap(dev->parent, NULL);
	if (!regmap)
		return dev_err_probe(dev, -ENODEV, "no regmap\n");
	ret = of_property_read_u32(dev->of_node, "reg", &base);
	if (ret)
		return dev_err_probe(dev, ret, "no base address\n");

	for_each_child_of_node_scoped(dev->of_node, child) {
		tsen = devm_kzalloc(dev, sizeof(*tsen), GFP_KERNEL);
		if (!tsen)
			return -ENOMEM;
		tsen->regmap = regmap;
		tsen->base = base;
		tsen->cali_mode = cali;
		ret = of_property_read_u32(child, "reg", &tsen->id);
		if (ret)
			return dev_err_probe(dev, ret, "no reg in %pOF\n", child);
		tz = devm_thermal_of_zone_register(dev, tsen->id, tsen, &ump96xx_tsensor_ops);
		if (IS_ERR(tz)) {
			/* a sensor no zone refers to */
			if (PTR_ERR(tz) == -ENODEV)
				continue;
			return dev_err_probe(dev, PTR_ERR(tz), "cannot register sensor %u\n", tsen->id);
		}
	}
	if (!cali) {
		dev_info(dev, "not in calibration mode: the sensors are not read (as on 5.4)\n");
		return 0;
	}
	/* calibration mode: the vendor driver switched the block off again after setting up its zones */
	return ump96xx_tsensor_disable(regmap, base);
}

static const struct of_device_id ump96xx_tsen_of_match[] = {
	{ .compatible = "sprd,ump9622-tsensor" },
	{ }
};
MODULE_DEVICE_TABLE(of, ump96xx_tsen_of_match);

static struct platform_driver ump96xx_tsen_driver = {
	.probe = ump96xx_tsen_probe,
	.driver = {
		.name = "ump96xx-tsensor",
		.of_match_table = ump96xx_tsen_of_match,
	},
};
module_platform_driver(ump96xx_tsen_driver);

MODULE_DESCRIPTION("Unisoc UMP96xx temperature sensors");
MODULE_LICENSE("GPL");
