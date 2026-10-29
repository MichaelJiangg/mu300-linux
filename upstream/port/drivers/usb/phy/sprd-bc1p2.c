// SPDX-License-Identifier: GPL-2.0+
/*
 * Unisoc UMP9620 BC1.2 charger-port detection (bc1p2@239c): what the PMIC's detector found on VBUS - a standard
 * (SDP), charging (CDP) or dedicated (DCP) port.
 *
 * Ported from the Unisoc 5.4 kernel (drivers/usb/phy/sprd-bc1p2.c, Yongzhi Chen). The probe does what 5.4's does
 * (the charger interrupt's delay set to 128 ms) and sprd_bc1p2_charger_detect() reads the result as 5.4's first
 * detection does, for a USB PHY driver to call. What 5.4's PHY did with it - the charge current for charger-manager
 * - is the U30 Air's charger's own business on mainline (patch 0009 reads the same register through the PMIC
 * driver); here the result is also in the device's charger_type file ("SDP", "CDP", "DCP", "unknown"; "absent"
 * without VBUS). The re-detection 5.4 can start drives D+/D-, so nothing here starts it.
 */
#include <linux/delay.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <uapi/linux/usb/charger.h>

#define UMP9620_CHARGE_STATUS		0x239c
#define UMP9620_CHG_DET_FGU_CTRL	0x23a0

#define BIT_CHG_DET_DONE		BIT(11)
#define BIT_SDP_INT			BIT(7)
#define BIT_DCP_INT			BIT(6)
#define BIT_CDP_INT			BIT(5)
#define BIT_CHGR_INT			BIT(2)

#define CHG_INT_DELAY_128MS		2
#define UMP96XX_CHG_INT_DELAY_MASK	GENMASK(11, 8)
#define UMP96XX_CHG_INT_DELAY_OFFSET	8
#define UMP96XX_CHG_DET_RETRY_COUNT	60
#define UMP96XX_CHG_DET_DELAY_MS	20

struct sprd_bc1p2 {
	struct regmap *regmap;
	struct mutex lock;
};

static struct sprd_bc1p2 *bc1p2;

static enum usb_charger_type sprd_bc1p2_type(u32 val)
{
	switch (val & (BIT_CDP_INT | BIT_DCP_INT | BIT_SDP_INT)) {
	case BIT_CDP_INT:
		return CDP_TYPE;
	case BIT_DCP_INT:
		return DCP_TYPE;
	case BIT_SDP_INT:
		return SDP_TYPE;
	default:
		return UNKNOWN_TYPE;
	}
}

/*
 * 5.4's sprd_bc1p2_detect(): wait up to 1.2 s for the detector to finish while a charger is there; UNKNOWN_TYPE
 * without one (*present false) or when it does not finish
 */
enum usb_charger_type sprd_bc1p2_charger_detect_state(bool *present)
{
	enum usb_charger_type type = UNKNOWN_TYPE;
	int cnt = UMP96XX_CHG_DET_RETRY_COUNT;
	u32 val = 0;

	if (!bc1p2)
		return UNKNOWN_TYPE;
	mutex_lock(&bc1p2->lock);
	do {
		if (regmap_read(bc1p2->regmap, UMP9620_CHARGE_STATUS, &val))
			break;
		if (!(val & BIT_CHGR_INT))
			break;
		if (val & BIT_CHG_DET_DONE) {
			type = sprd_bc1p2_type(val);
			break;
		}
		msleep(UMP96XX_CHG_DET_DELAY_MS);
	} while (--cnt > 0);
	mutex_unlock(&bc1p2->lock);
	if (present)
		*present = val & BIT_CHGR_INT;
	return type;
}
EXPORT_SYMBOL_GPL(sprd_bc1p2_charger_detect_state);

static ssize_t charger_type_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	static const char * const names[] = {
		[UNKNOWN_TYPE] = "unknown", [SDP_TYPE] = "SDP", [DCP_TYPE] = "DCP",
		[CDP_TYPE] = "CDP", [ACA_TYPE] = "ACA",
	};
	bool present;
	enum usb_charger_type t = sprd_bc1p2_charger_detect_state(&present);

	if (!present)
		return sysfs_emit(buf, "absent\n");
	return sysfs_emit(buf, "%s\n", t < ARRAY_SIZE(names) && names[t] ? names[t] : "unknown");
}
static DEVICE_ATTR_RO(charger_type);

static struct attribute *sprd_bc1p2_attrs[] = {
	&dev_attr_charger_type.attr,
	NULL
};
ATTRIBUTE_GROUPS(sprd_bc1p2);

static int sprd_bc1p2_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct sprd_bc1p2 *b;
	int ret;

	b = devm_kzalloc(dev, sizeof(*b), GFP_KERNEL);
	if (!b)
		return -ENOMEM;
	b->regmap = dev_get_regmap(dev->parent, NULL);
	if (!b->regmap)
		return dev_err_probe(dev, -ENODEV, "no regmap\n");
	mutex_init(&b->lock);
	/* as 5.4: the charger interrupt 128 ms after VBUS */
	ret = regmap_update_bits(b->regmap, UMP9620_CHG_DET_FGU_CTRL, UMP96XX_CHG_INT_DELAY_MASK,
				 CHG_INT_DELAY_128MS << UMP96XX_CHG_INT_DELAY_OFFSET);
	if (ret)
		return ret;
	bc1p2 = b;
	return 0;
}

static void sprd_bc1p2_remove(struct platform_device *pdev)
{
	bc1p2 = NULL;
}

static const struct of_device_id sprd_bc1p2_of_match[] = {
	{ .compatible = "sprd,ump9620-bc1p2" },
	{ }
};
MODULE_DEVICE_TABLE(of, sprd_bc1p2_of_match);

static struct platform_driver sprd_bc1p2_driver = {
	.driver = {
		.name = "sprd-bc1p2",
		.of_match_table = sprd_bc1p2_of_match,
		.dev_groups = sprd_bc1p2_groups,
	},
	.probe = sprd_bc1p2_probe,
	.remove = sprd_bc1p2_remove,
};
module_platform_driver(sprd_bc1p2_driver);

MODULE_DESCRIPTION("Unisoc UMP9620 BC1.2 charger-port detection");
MODULE_LICENSE("GPL");
