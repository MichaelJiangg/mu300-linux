// SPDX-License-Identifier: GPL-2.0 OR BSD-2-Clause
/*
 * ZTE board state: the board ID and the secure-boot (eFuse) state the bootloader passes on its command line
 * (androidboot.zte_boardid=, efuse_state=), as /proc/driver/board_id, /dev/zte_board_state with its secstate
 * attribute, and zte_get_boardid()/zte_get_efuse_state() for other drivers.
 *
 * Ported from the ZTE 5.4 kernel (drivers/vendor/soc/sprd/board_state/board_state.c). Mainline forces its own
 * command line, so, as on 5.4, the values are read from the device tree's /chosen/bootargs, which still holds the
 * bootloader's. The misc device's open and ioctl do nothing, as on 5.4.
 */
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/string.h>

#define BOARDID_CMDLINE_STR	"androidboot.zte_boardid="
#define EFUSE_STATE_CMDLINE_STR	"efuse_state="
#define EFUSE_ENABLE_VALUE	5

static int boardid = -1;
static int efuse_state = -1;

/* the number after KEY in the command line, as 5.4 parsed it (kstrtol base 0, at most 15 characters) */
static int cmdline_value(const char *cmdline, const char *key, long *value)
{
	const char *p = strstr(cmdline, key);
	char buf[16];
	size_t n;

	if (!p)
		return -ENOENT;
	p += strlen(key);
	p = skip_spaces(p);
	n = strcspn(p, " \t\n");
	if (!n || n >= sizeof(buf))
		return -EINVAL;
	memcpy(buf, p, n);
	buf[n] = '\0';
	return kstrtol(buf, 0, value);
}

int zte_get_boardid(void)
{
	return boardid;
}
EXPORT_SYMBOL(zte_get_boardid);

int zte_get_efuse_state(void)
{
	return efuse_state;
}
EXPORT_SYMBOL(zte_get_efuse_state);

static ssize_t secstate_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%d\n", efuse_state);
}
static DEVICE_ATTR_RO(secstate);

static struct attribute *zte_board_state_attrs[] = {
	&dev_attr_secstate.attr,
	NULL
};
ATTRIBUTE_GROUPS(zte_board_state);

static int zte_board_state_open(struct inode *inode, struct file *file)
{
	return 0;
}

static long zte_board_state_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	return 0;
}

static const struct file_operations zte_board_state_fops = {
	.owner = THIS_MODULE,
	.open = zte_board_state_open,
	.unlocked_ioctl = zte_board_state_ioctl,
};

static struct miscdevice zte_board_state_dev = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "zte_board_state",
	.fops = &zte_board_state_fops,
	.groups = zte_board_state_groups,
};

static int board_id_show(struct seq_file *m, void *v)
{
	seq_printf(m, "%d\n", boardid);
	return 0;
}

static int __init zte_board_state_init(void)
{
	struct device_node *chosen;
	const char *cmdline = NULL;
	long v;
	int ret;

	chosen = of_find_node_by_path("/chosen");
	ret = chosen ? of_property_read_string(chosen, "bootargs", &cmdline) : -ENOENT;
	of_node_put(chosen);
	if (ret) {
		pr_err("[ZTE_LDD_BOOT][BOARDSTATE][ERR] no bootargs in /chosen\n");
		return ret;
	}
	if (!cmdline_value(cmdline, BOARDID_CMDLINE_STR, &v))
		boardid = v;
	if (!cmdline_value(cmdline, EFUSE_STATE_CMDLINE_STR, &v))
		efuse_state = v == EFUSE_ENABLE_VALUE;

	ret = misc_register(&zte_board_state_dev);
	if (ret) {
		pr_err("[ZTE_LDD_BOOT][BOARDSTATE][ERR] cannot register the misc device: %d\n", ret);
		return ret;
	}
	if (!proc_create_single("driver/board_id", 0444, NULL, board_id_show))
		pr_warn("[ZTE_LDD_BOOT][BOARDSTATE][WARN] cannot create /proc/driver/board_id\n");
	pr_info("[ZTE_LDD_BOOT][BOARDSTATE][INFO] board id %d, secure boot %d\n", boardid, efuse_state);
	return 0;
}
module_init(zte_board_state_init);

MODULE_LICENSE("Dual BSD/GPL");
MODULE_DESCRIPTION("ZTE board state");
