// SPDX-License-Identifier: GPL-2.0-only
/*
 * Unisoc UMP9621 and UMP9622: the two companion PMICs of the UMP9620 (pmic@1 and pmic@2 on the ADI bus).
 *
 * They answer on the same ADI bus as the UMP9620, at register offsets 0x8000 (UMP9621) and 0xc000 (UMP9622), and
 * have no interrupts. This driver gives each a regmap with that offset and populates its device tree sub-nodes,
 * which take the regmap from their parent: the UMP9621's regulators (vddcpu0, vddsram1/2, vddai, vddmm,
 * DCDC_MODEM), its eFuse and global registers, the UMP9622's temperature sensors and global registers.
 *
 * From the Unisoc 5.4 kernel's MFD (drivers/mfd/sprd-ump96xx-spi.c, Luyao Wu), which handles all three PMICs; on
 * mainline the UMP9620 stays with sprd-sc27xx-spi (patched in upstream/port/install.py), and this driver takes the
 * other two. Its name is the 5.4 driver's.
 */
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mod_devicetable.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/regmap.h>
#include <linux/slab.h>
#include <linux/spi/spi.h>

struct ump962x_pmic {
	u32 slave_id;
};

static int ump962x_spi_write(void *context, const void *data, size_t count)
{
	struct spi_device *spi = to_spi_device(context);
	const struct ump962x_pmic *p = spi_get_drvdata(spi);
	u32 buf[2];

	/* one register and its value: the ADI controller takes them as two words */
	if (count != sizeof(buf))
		return -EINVAL;
	memcpy(buf, data, count);
	buf[0] += p->slave_id;
	return spi_write(spi, buf, count);
}

static int ump962x_spi_read(void *context, const void *reg, size_t reg_size, void *val, size_t val_size)
{
	struct spi_device *spi = to_spi_device(context);
	const struct ump962x_pmic *p = spi_get_drvdata(spi);
	u32 rx_buf[2] = { 0 };
	int ret;

	if (reg_size != sizeof(u32) || val_size != sizeof(u32))
		return -EINVAL;
	memcpy(rx_buf, reg, sizeof(u32));
	rx_buf[0] += p->slave_id;
	ret = spi_read(spi, rx_buf, 1);
	if (ret < 0)
		return ret;
	memcpy(val, rx_buf, val_size);
	return 0;
}

static const struct regmap_bus ump962x_regmap_bus = {
	.write = ump962x_spi_write,
	.read = ump962x_spi_read,
	.reg_format_endian_default = REGMAP_ENDIAN_NATIVE,
	.val_format_endian_default = REGMAP_ENDIAN_NATIVE,
};

static const struct regmap_config ump962x_regmap_config = {
	.reg_bits = 32,
	.val_bits = 32,
	.reg_stride = 4,
	.max_register = 0x3fff,
};

static int ump962x_probe(struct spi_device *spi)
{
	struct ump962x_pmic *p;
	struct regmap *map;

	p = devm_kzalloc(&spi->dev, sizeof(*p), GFP_KERNEL);
	if (!p)
		return -ENOMEM;
	p->slave_id = (uintptr_t)spi_get_device_match_data(spi);
	spi_set_drvdata(spi, p);
	map = devm_regmap_init(&spi->dev, &ump962x_regmap_bus, &spi->dev, &ump962x_regmap_config);
	if (IS_ERR(map))
		return dev_err_probe(&spi->dev, PTR_ERR(map), "cannot set up the register map\n");
	return devm_of_platform_populate(&spi->dev);
}

static const struct of_device_id ump962x_of_match[] = {
	{ .compatible = "sprd,ump9621", .data = (void *)0x8000 },
	{ .compatible = "sprd,ump9622", .data = (void *)0xc000 },
	{ }
};
MODULE_DEVICE_TABLE(of, ump962x_of_match);

static const struct spi_device_id ump962x_spi_ids[] = {
	{ "ump9621", 0x8000 },
	{ "ump9622", 0xc000 },
	{ }
};
MODULE_DEVICE_TABLE(spi, ump962x_spi_ids);

static struct spi_driver ump962x_driver = {
	.driver = {
		.name = "ump96xx-pmic",
		.of_match_table = ump962x_of_match,
	},
	.probe = ump962x_probe,
	.id_table = ump962x_spi_ids,
};

static int __init ump962x_init(void)
{
	return spi_register_driver(&ump962x_driver);
}
subsys_initcall(ump962x_init);

static void __exit ump962x_exit(void)
{
	spi_unregister_driver(&ump962x_driver);
}
module_exit(ump962x_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unisoc UMP9621/UMP9622 companion PMICs");
