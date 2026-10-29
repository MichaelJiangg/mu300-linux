// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc PMIC global registers (syscon@2000 of pmic@0, pmic@1 and pmic@2): one register read or written through
 * sysfs, as the Unisoc 5.4 kernel's sprd_pmic_syscon (drivers/soc/sprd/sprd_pmic_syscon.c, Luyao Wu) did it:
 *
 *   /sys/bus/platform/drivers/sprd-pmic-glb/<compatible>/pmic_reg     the register (hex), at or above the block's base
 *   /sys/bus/platform/drivers/sprd-pmic-glb/<compatible>/pmic_value   its value (hex), read or written
 *
 * Root only, as on 5.4 (0644). A register is read only when asked for, one at a time.
 */
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/kobject.h>
#include <linux/list.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/sysfs.h>

#include "../../base/base.h"

struct pmic_glb {
	u32 reg;
	u32 base;
	struct kobject *kobj;
	struct regmap *regmap;
	struct list_head list;
};

static LIST_HEAD(glb_list);
static DEFINE_MUTEX(glb_lock);
static struct platform_driver sprd_pmic_glb_driver;

static struct pmic_glb *glb_of(struct kobject *kobj)
{
	struct pmic_glb *g;

	list_for_each_entry(g, &glb_list, list)
		if (g->kobj == kobj)
			return g;
	return NULL;
}

static ssize_t pmic_reg_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	struct pmic_glb *g;
	ssize_t ret = -EINVAL;

	mutex_lock(&glb_lock);
	g = glb_of(kobj);
	if (g)
		ret = sysfs_emit(buf, "0x%x", g->reg);
	mutex_unlock(&glb_lock);
	return ret;
}

static ssize_t pmic_reg_store(struct kobject *kobj, struct kobj_attribute *attr, const char *buf, size_t count)
{
	struct pmic_glb *g;
	ssize_t ret = -EINVAL;
	u32 reg;

	if (sscanf(buf, "%x", &reg) != 1)
		return -EINVAL;
	mutex_lock(&glb_lock);
	g = glb_of(kobj);
	if (g) {
		g->reg = reg;
		ret = count;
	}
	mutex_unlock(&glb_lock);
	return ret;
}

static ssize_t pmic_value_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	struct pmic_glb *g;
	ssize_t ret = -EINVAL;
	u32 value;

	mutex_lock(&glb_lock);
	g = glb_of(kobj);
	if (g && g->reg >= g->base) {
		ret = regmap_read(g->regmap, g->reg, &value);
		if (!ret)
			ret = sysfs_emit(buf, "%x", value);
	}
	mutex_unlock(&glb_lock);
	return ret;
}

static ssize_t pmic_value_store(struct kobject *kobj, struct kobj_attribute *attr, const char *buf, size_t count)
{
	struct pmic_glb *g;
	ssize_t ret = -EINVAL;
	u32 value;

	if (sscanf(buf, "%x", &value) != 1)
		return -EINVAL;
	mutex_lock(&glb_lock);
	g = glb_of(kobj);
	if (g && g->reg >= g->base) {
		ret = regmap_write(g->regmap, g->reg, value);
		if (!ret)
			ret = count;
	}
	mutex_unlock(&glb_lock);
	return ret;
}

static struct kobj_attribute pmic_reg_attr = __ATTR(pmic_reg, 0644, pmic_reg_show, pmic_reg_store);
static struct kobj_attribute pmic_value_attr = __ATTR(pmic_value, 0644, pmic_value_show, pmic_value_store);

static struct attribute *pmic_syscon_attrs[] = {
	&pmic_reg_attr.attr,
	&pmic_value_attr.attr,
	NULL
};

static const struct attribute_group pmic_syscon_group = {
	.attrs = pmic_syscon_attrs,
};

static int sprd_pmic_glb_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	const char *compat;
	struct pmic_glb *g;
	int ret;

	g = devm_kzalloc(dev, sizeof(*g), GFP_KERNEL);
	if (!g)
		return -ENOMEM;
	g->regmap = dev_get_regmap(dev->parent, NULL);
	if (!g->regmap)
		return dev_err_probe(dev, -ENODEV, "no regmap\n");
	ret = of_property_read_u32_index(dev->of_node, "reg", 0, &g->base);
	if (ret)
		return dev_err_probe(dev, ret, "no base register\n");
	ret = of_property_read_string(dev->of_node, "compatible", &compat);
	if (ret)
		return ret;

	/* named after the node's compatible, under the driver's directory, as on 5.4 */
	g->kobj = kobject_create_and_add(compat, &sprd_pmic_glb_driver.driver.p->kobj);
	if (!g->kobj)
		return -ENOMEM;
	ret = sysfs_create_group(g->kobj, &pmic_syscon_group);
	if (ret) {
		kobject_put(g->kobj);
		return ret;
	}
	mutex_lock(&glb_lock);
	list_add(&g->list, &glb_list);
	mutex_unlock(&glb_lock);
	platform_set_drvdata(pdev, g);
	return 0;
}

static void sprd_pmic_glb_remove(struct platform_device *pdev)
{
	struct pmic_glb *g = platform_get_drvdata(pdev);

	mutex_lock(&glb_lock);
	list_del(&g->list);
	mutex_unlock(&glb_lock);
	sysfs_remove_group(g->kobj, &pmic_syscon_group);
	kobject_put(g->kobj);
}

static const struct of_device_id sprd_pmic_glb_match[] = {
	{ .compatible = "sprd,sc27xx-syscon" },
	{ .compatible = "sprd,ump962x-syscon" },
	{ .compatible = "sprd,ump9621-syscon" },
	{ .compatible = "sprd,ump9622-syscon" },
	{ }
};
MODULE_DEVICE_TABLE(of, sprd_pmic_glb_match);

static struct platform_driver sprd_pmic_glb_driver = {
	.probe = sprd_pmic_glb_probe,
	.remove = sprd_pmic_glb_remove,
	.driver = {
		.name = "sprd-pmic-glb",
		.of_match_table = sprd_pmic_glb_match,
	},
};
module_platform_driver(sprd_pmic_glb_driver);

MODULE_DESCRIPTION("Unisoc PMIC global registers");
MODULE_LICENSE("GPL");
