// SPDX-License-Identifier: GPL-2.0-only
/* Restore the stock virtual-thermal zone using its DT sensor list/trips/maps.
 * Physical sensors are built into both supported MU300 mainline kernels.
 * No invented temperatures, DT rewrites, or additional polling worker.
 */
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/thermal.h>

struct mu300_virtual {
	unsigned int count;
	struct thermal_zone_device *sensor[];
};

static int mu300_virtual_temp(struct thermal_zone_device *tz, int *temp)
{
	struct mu300_virtual *v = thermal_zone_device_priv(tz);
	int hottest = INT_MIN, value, ret;
	unsigned int i;

	for (i = 0; i < v->count; i++) {
		ret = thermal_zone_get_temp(v->sensor[i], &value);
		if (ret)
			continue; /* A broken sensor must not hide the other hot readings. */
		hottest = max(hottest, value);
	}
	if (hottest == INT_MIN)
		return -EIO; /* No valid sensor: never report a fabricated cold reading. */
	*temp = hottest;
	return 0;
}

static const struct thermal_zone_device_ops mu300_virtual_ops = {
	.get_temp = mu300_virtual_temp,
};

static int mu300_virtual_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *node;
	struct thermal_zone_device *tz;
	struct mu300_virtual *v;
	int count, i;

	if (!of_machine_is_compatible("sprd,ums9620"))
		return -ENODEV;
	count = of_count_phandle_with_args(dev->of_node, "thmzone-cells", NULL);
	if (count <= 0 || count > 32)
		return -EINVAL;
	v = devm_kzalloc(dev, struct_size(v, sensor, count), GFP_KERNEL);
	if (!v)
		return -ENOMEM;
	v->count = count;
	for (i = 0; i < count; i++) {
		node = of_parse_phandle(dev->of_node, "thmzone-cells", i);
		if (!node)
			return -EINVAL;
		v->sensor[i] = thermal_zone_get_zone_by_name(node->name);
		of_node_put(node);
		if (IS_ERR(v->sensor[i]))
			return dev_err_probe(dev, -EPROBE_DEFER, "physical thermal zone not ready\n");
	}
	tz = devm_thermal_of_zone_register(dev, 0, v, &mu300_virtual_ops);
	if (IS_ERR(tz))
		return dev_err_probe(dev, PTR_ERR(tz), "virtual thermal registration failed\n");
	dev_info(dev, "stock virtual thermal zone active (%d sensors)\n", count);
	return 0;
}

static const struct of_device_id mu300_virtual_match[] = {
	{ .compatible = "virtual-thermal" },
	{ }
};
MODULE_DEVICE_TABLE(of, mu300_virtual_match);

static struct platform_driver mu300_virtual_driver = {
	.probe = mu300_virtual_probe,
	.driver = {
		.name = "mu300-virtual-thermal",
		.of_match_table = mu300_virtual_match,
		.suppress_bind_attrs = true,
	},
};
module_platform_driver(mu300_virtual_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("MU300 stock virtual thermal sensor for mainline kernels");
