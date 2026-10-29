// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc SoC identity: the chip's ID registers (the "sprd,soc-id" node, socid under aon) and the SoC model and
 * manufacturer the device tree's root names (soc-module, soc-manufacturer).
 *
 * Ported from the Unisoc 5.4 kernel, where two drivers did this: sprd_soc_id (drivers/misc/sprd_soc_id.c, Luting
 * Guo; /proc/socid/socid_inf and sprd_get_soc_id()) and sprd_manufacturer_model (drivers/soc/sprd/, Shian Wang;
 * /sys/devices/soc0/soc_model and soc_manufacturer). Both are here, with the same files and the same text in them.
 * On mainline /sys/devices/soc0 is a SoC device (soc_device_register()), so it also carries the standard
 * attributes: machine (the board's model), family, soc_id and revision.
 */
#include <linux/err.h>
#include <linux/init.h>
#include <linux/mfd/syscon.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/proc_fs.h>
#include <linux/regmap.h>
#include <linux/seq_file.h>
#include <linux/slab.h>
#include <linux/sprd_soc_id.h>
#include <linux/sys_soc.h>

static const char * const syscon_name[] = {
	"chip_id",
	"plat_id",
	"implement_id",
	"manufacture_id",
	"version_id",
};

struct register_gpr {
	struct regmap *gpr;
	u32 reg;
	u32 mask;
};

static struct register_gpr syscon_regs[ARRAY_SIZE(syscon_name)];
static const char *soc_model, *soc_manufacturer;
static struct soc_device *soc_dev;

int sprd_get_soc_id(sprd_soc_id_type_t soc_id_type, u32 *id, int id_len)
{
	struct register_gpr *r;
	int ret;

	if (soc_id_type < 0 || soc_id_type >= ARRAY_SIZE(syscon_regs) || id_len < 1)
		return -EINVAL;
	r = &syscon_regs[soc_id_type];
	if (!r->gpr)
		return -ENODEV;
	switch (soc_id_type) {
	case AON_CHIP_ID:
	case AON_PLAT_ID:
		/* two words, as on 5.4 */
		if (id_len < 2)
			return -EINVAL;
		ret = regmap_read(r->gpr, r->reg, &id[0]);
		if (!ret)
			ret = regmap_read(r->gpr, r->reg + 4, &id[1]);
		break;
	default:
		ret = regmap_read(r->gpr, r->reg, id);
		break;
	}
	return ret ? -EINVAL : 0;
}
EXPORT_SYMBOL(sprd_get_soc_id);

/* /proc/socid/socid_inf: the 5.4 text, one ID per line (the chip and platform IDs are two words) */
static int socid_inf_show(struct seq_file *m, void *v)
{
	u32 value[2];
	int i;

	for (i = 0; i < ARRAY_SIZE(syscon_name); i++) {
		value[0] = value[1] = 0;
		sprd_get_soc_id(i, value, 2);
		seq_printf(m, "%s 0x%x", syscon_name[i], value[0]);
		if (i <= AON_PLAT_ID)
			seq_printf(m, "  0x%x", value[1]);
		seq_putc(m, '\n');
	}
	return 0;
}

/* /sys/devices/soc0/soc_model and soc_manufacturer, word for word as sprd_manufacturer_model wrote them (the
 * second one's label included) */
static ssize_t soc_model_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "soc_model: %s \n", soc_model ?: "(null)");
}
static DEVICE_ATTR_RO(soc_model);

static ssize_t soc_manufacturer_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "soc_model: %s \n", soc_manufacturer ?: "(null)");
}
static DEVICE_ATTR_RO(soc_manufacturer);

static struct attribute *sprd_soc_attrs[] = {
	&dev_attr_soc_model.attr,
	&dev_attr_soc_manufacturer.attr,
	NULL
};
ATTRIBUTE_GROUPS(sprd_soc);

static int sprd_soc_id_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node, *root;
	struct soc_device_attribute *attr;
	struct soc_device *soc;
	struct proc_dir_entry *procdir;
	u32 args[2], chip[2] = { 0, 0 }, ver = 0;
	int i;

	for (i = 0; i < ARRAY_SIZE(syscon_name); i++) {
		struct regmap *map = syscon_regmap_lookup_by_phandle_args(np, syscon_name[i], 2, args);

		if (IS_ERR_OR_NULL(map)) {
			dev_warn(dev, "no %s register\n", syscon_name[i]);
			continue;
		}
		syscon_regs[i].gpr = map;
		syscon_regs[i].reg = args[0];
		syscon_regs[i].mask = args[1];
	}

	root = of_find_node_by_path("/");
	if (root) {
		of_property_read_string(root, "soc-module", &soc_model);
		of_property_read_string(root, "soc-manufacturer", &soc_manufacturer);
		of_node_put(root);
	}

	procdir = proc_mkdir("socid", NULL);
	if (!procdir || !proc_create_single("socid_inf", 0444, procdir, socid_inf_show))
		dev_warn(dev, "cannot create /proc/socid/socid_inf\n");

	attr = devm_kzalloc(dev, sizeof(*attr), GFP_KERNEL);
	if (!attr)
		return -ENOMEM;
	sprd_get_soc_id(AON_CHIP_ID, chip, 2);
	sprd_get_soc_id(AON_VER_ID, &ver, 1);
	attr->family = devm_kstrdup(dev, soc_manufacturer ?: "Unisoc", GFP_KERNEL);
	attr->soc_id = devm_kasprintf(dev, GFP_KERNEL, "%s", soc_model ?: "unknown");
	attr->revision = devm_kasprintf(dev, GFP_KERNEL, "0x%x", ver & (syscon_regs[AON_VER_ID].mask ?: ~0U));
	attr->serial_number = NULL;
	attr->custom_attr_group = sprd_soc_groups[0];
	soc = soc_device_register(attr);
	if (IS_ERR(soc)) {
		remove_proc_subtree("socid", NULL);
		return dev_err_probe(dev, PTR_ERR(soc), "cannot register the SoC device\n");
	}
	soc_dev = soc;
	dev_info(dev, "%s %s, chip id 0x%x 0x%x, version 0x%x\n", attr->family, attr->soc_id, chip[0], chip[1], ver);
	return 0;
}

static void sprd_soc_id_remove(struct platform_device *pdev)
{
	soc_device_unregister(soc_dev);
	remove_proc_subtree("socid", NULL);
	memset(syscon_regs, 0, sizeof(syscon_regs));
}

static const struct of_device_id sprd_soc_id_of_match[] = {
	{ .compatible = "sprd,soc-id" },
	{ }
};
MODULE_DEVICE_TABLE(of, sprd_soc_id_of_match);

static struct platform_driver sprd_soc_id_driver = {
	.probe = sprd_soc_id_probe,
	.remove = sprd_soc_id_remove,
	.driver = {
		.name = "sprd-soc-id",
		.of_match_table = sprd_soc_id_of_match,
	},
};
module_platform_driver(sprd_soc_id_driver);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unisoc SoC ID and model");
