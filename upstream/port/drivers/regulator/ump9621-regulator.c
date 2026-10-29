// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc UMP9621 (the UMS9620's second PMIC, pmic@1) regulators: the DC-DC converters of the CPU's little cluster
 * (vddcpu0), the SRAMs (vddsram1/2), the AI and multimedia domains (vddai, vddmm) and the modem (DCDC_MODEM).
 *
 * Ported from the Unisoc 5.4 kernel (drivers/regulator/ump9621-regulator.c, Zhongfa Wang): the same registers,
 * steps and write-protection unlock. Left out: the vendor's own debugfs files (the regulator core has its own) and
 * the telemetry uevent it sent when a voltage below 0.3 V was set. The registers come through the parent's regmap
 * (upstream/port/drivers/mfd/ump962x-pmic.c), which adds the PMIC's offset.
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/regulator/driver.h>
#include <linux/regulator/of_regulator.h>

#define UMP9621_REGULATOR_BASE		0x2000

/* write protection of the power registers */
#define UMP9621_WR_UNLOCK_VALUE		0x6e7f
#define UMP9621_PWR_WR_PROT		(UMP9621_REGULATOR_BASE + 0x134)

/* enable (power-down) register and bits */
#define UMP9621_POWER_PD_SW		(UMP9621_REGULATOR_BASE + 0x01c)
#define UMP9621_DCDC_SRAM1_PD_MASK	BIT(8)
#define UMP9621_DCDC_SRAM2_PD_MASK	BIT(7)
#define UMP9621_DCDC_AI_PD_MASK		BIT(5)
#define UMP9621_DCDC_MODEM_PD_MASK	BIT(4)
#define UMP9621_DCDC_CPU0_PD_MASK	BIT(2)
#define UMP9621_DCDC_MM_PD_MASK		BIT(1)

/* voltage select registers */
#define UMP9621_DCDC_SRAM1_VOL		(UMP9621_REGULATOR_BASE + 0x0e8)
#define UMP9621_DCDC_SRAM2_VOL		(UMP9621_REGULATOR_BASE + 0x74)
#define UMP9621_DCDC_AI_VOL		(UMP9621_REGULATOR_BASE + 0x1a0)
#define UMP9621_DCDC_MODEM_VOL		(UMP9621_REGULATOR_BASE + 0x54)
#define UMP9621_DCDC_CPU0_VOL		(UMP9621_REGULATOR_BASE + 0x44)
#define UMP9621_DCDC_MM_VOL		(UMP9621_REGULATOR_BASE + 0x180)
#define UMP9621_DCDC_VOL_MASK		GENMASK(8, 0)

enum ump9621_regulator_id {
	UMP9621_DCDC_SRAM1,
	UMP9621_DCDC_SRAM2,
	UMP9621_DCDC_BOB,
	UMP9621_DCDC_AI,
	UMP9621_DCDC_MODEM,
	UMP9621_DCDC_CPU0,
	UMP9621_DCDC_MM,
};

static const struct regulator_ops ump9621_regu_linear_ops = {
	.enable = regulator_enable_regmap,
	.disable = regulator_disable_regmap,
	.is_enabled = regulator_is_enabled_regmap,
	.list_voltage = regulator_list_voltage_linear,
	.get_voltage_sel = regulator_get_voltage_sel_regmap,
	.set_voltage_sel = regulator_set_voltage_sel_regmap,
};

/* 0 to 1.596875 V in steps of 3.125 mV, enabled while the power-down bit is clear */
#define UMP9621_DCDC(_id) {						\
	.name			= #_id,					\
	.of_match		= of_match_ptr(#_id),			\
	.ops			= &ump9621_regu_linear_ops,		\
	.type			= REGULATOR_VOLTAGE,			\
	.id			= UMP9621_##_id,			\
	.owner			= THIS_MODULE,				\
	.min_uV			= 0,					\
	.n_voltages		= 1596875 / 3125 + 1,			\
	.uV_step		= 3125,					\
	.enable_is_inverted	= true,					\
	.enable_val		= 0,					\
	.enable_reg		= UMP9621_POWER_PD_SW,			\
	.enable_mask		= UMP9621_##_id##_PD_MASK,		\
	.vsel_reg		= UMP9621_##_id##_VOL,			\
	.vsel_mask		= UMP9621_DCDC_VOL_MASK,		\
}

static const struct regulator_desc regulators[] = {
	UMP9621_DCDC(DCDC_SRAM1),
	UMP9621_DCDC(DCDC_SRAM2),
	UMP9621_DCDC(DCDC_AI),
	UMP9621_DCDC(DCDC_MODEM),
	UMP9621_DCDC(DCDC_CPU0),
	UMP9621_DCDC(DCDC_MM),
};

static int ump9621_regulator_probe(struct platform_device *pdev)
{
	struct regulator_config config = { };
	struct regulator_dev *rdev;
	struct regmap *regmap;
	int i, ret;

	regmap = dev_get_regmap(pdev->dev.parent, NULL);
	if (!regmap)
		return dev_err_probe(&pdev->dev, -ENODEV, "no regmap\n");

	ret = regmap_write(regmap, UMP9621_PWR_WR_PROT, UMP9621_WR_UNLOCK_VALUE);
	if (ret)
		return dev_err_probe(&pdev->dev, ret, "cannot release the regulator lock\n");

	config.dev = &pdev->dev;
	config.regmap = regmap;
	for (i = 0; i < ARRAY_SIZE(regulators); i++) {
		rdev = devm_regulator_register(&pdev->dev, &regulators[i], &config);
		if (IS_ERR(rdev))
			return dev_err_probe(&pdev->dev, PTR_ERR(rdev), "cannot register %s\n",
					     regulators[i].name);
	}
	return 0;
}

static const struct of_device_id ump9621_regulator_match[] = {
	{ .compatible = "sprd,ump9621-regulator" },
	{ }
};
MODULE_DEVICE_TABLE(of, ump9621_regulator_match);

static struct platform_driver ump9621_regulator_driver = {
	.driver = {
		.name = "ump9621-regulator",
		.of_match_table = ump9621_regulator_match,
	},
	.probe = ump9621_regulator_probe,
};
module_platform_driver(ump9621_regulator_driver);

MODULE_DESCRIPTION("Unisoc UMP9621 regulators");
MODULE_LICENSE("GPL");
