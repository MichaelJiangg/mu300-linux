// SPDX-License-Identifier: GPL-2.0
/*
 * ZTE card holder (tray) detection: /sys/zcard_det/zcard_det reads 1 with the tray in and 0 without.
 *
 * Ported from the ZTE 5.4 kernel (drivers/vendor/common/zcard_det/zte_card_holder_det.c, ZTE bsp light, 2022). It
 * takes the line from the first node with a "zcard-holder-det-gpios" property, or else from the first with
 * "cd-gpios" (on the F50 the card slot's detect line, the tray's), and reports its logical value (polarity
 * included). The 5.4 driver read the line without requesting it; mainline has to request it, and does so at
 * read time (see zcard_read()), so neither the GPIO controller's probe order nor the SD host's is in the way. A board with neither property (the U30 Air) gets no file, as on 5.4.
 */
#include <linux/err.h>
#include <linux/gpio/consumer.h>
#include <linux/init.h>
#include <linux/kobject.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/sysfs.h>

static struct device_node *zcard_np;
static const char *zcard_con;
/* the line as shared with its owner (the SD host); never freed here, the owner holds it */
static struct gpio_desc *zcard_shared;
static struct kobject *zcard_kobj;
static DEFINE_MUTEX(zcard_lock);

/*
 * The line's logical value. The card slot's host normally holds the line (its card detect): then it is shared
 * (asked for non-exclusively once, and kept). If nobody holds it, it is requested only for the read and given
 * back at once, so this file never keeps the SD host from getting its card detect.
 */
static int zcard_read(void)
{
	struct fwnode_handle *fw = of_fwnode_handle(zcard_np);
	struct gpio_desc *d;
	int v;

	mutex_lock(&zcard_lock);
	if (!zcard_shared) {
		d = fwnode_gpiod_get_index(fw, zcard_con, 0, GPIOD_ASIS, "zcard_det");
		if (!IS_ERR(d)) {
			v = gpiod_get_value_cansleep(d);
			gpiod_put(d);
			goto out;
		}
		if (PTR_ERR(d) != -EBUSY) {
			v = PTR_ERR(d) == -EPROBE_DEFER ? -EAGAIN : PTR_ERR(d);
			goto out;
		}
		d = fwnode_gpiod_get_index(fw, zcard_con, 0, GPIOD_ASIS | GPIOD_FLAGS_BIT_NONEXCLUSIVE,
					   "zcard_det");
		if (IS_ERR(d)) {
			v = PTR_ERR(d);
			goto out;
		}
		zcard_shared = d;
	}
	v = gpiod_get_value_cansleep(zcard_shared);
out:
	mutex_unlock(&zcard_lock);
	return v;
}

static ssize_t zcard_det_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	int v = zcard_read();

	if (v < 0)
		return v;
	return sysfs_emit(buf, "%d\n", v);
}
static struct kobj_attribute zcard_det_attr = __ATTR(zcard_det, 0444, zcard_det_show, NULL);

static int __init zte_card_holder_det_init(void)
{
	int ret;

	zcard_np = of_find_node_with_property(NULL, "zcard-holder-det-gpios");
	zcard_con = "zcard-holder-det";
	if (!zcard_np) {
		zcard_np = of_find_node_with_property(NULL, "cd-gpios");
		zcard_con = "cd";
	}
	if (!zcard_np) {
		pr_info("zcard_det: no card holder detect line on this board\n");
		return -ENODEV;
	}
	zcard_kobj = kobject_create_and_add("zcard_det", NULL);
	if (!zcard_kobj) {
		of_node_put(zcard_np);
		return -ENOMEM;
	}
	ret = sysfs_create_file(zcard_kobj, &zcard_det_attr.attr);
	if (ret) {
		kobject_put(zcard_kobj);
		of_node_put(zcard_np);
		return ret;
	}
	pr_info("zcard_det: card holder detect on %pOF (%s-gpios)\n", zcard_np, zcard_con);
	return 0;
}
module_init(zte_card_holder_det_init);

static void __exit zte_card_holder_det_exit(void)
{
	sysfs_remove_file(zcard_kobj, &zcard_det_attr.attr);
	kobject_put(zcard_kobj);
	of_node_put(zcard_np);
}
module_exit(zte_card_holder_det_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("ZTE card holder detection");
