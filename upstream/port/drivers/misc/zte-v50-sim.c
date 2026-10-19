// SPDX-License-Identifier: GPL-2.0-only
/* V50 sim_gpio_ctl binding, reconstructed from the stock B15 module.
 * GPIO0 is a card-detect INPUT, not a writable SIM selector. GPIO1 selects
 * eSIM2/eSIM3; GPIO2 selects eSIM1/pSIM. Honor stock chosen/bootargs selectors.
 * Userspace powers the affected SIM down through the existing AT owner
 * before changing either output. No modem commands or boot delays here.
 */
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>

struct v50_sim {
	struct gpio_desc *detect, *chip, *psim;
	struct mutex lock;
};

/* A live deployment must not switch a powered SIM as a side effect of probe.
 * Cold production boots keep the stock bootarg/default initialization. */
static bool preserve_state;
module_param(preserve_state, bool, 0444);
MODULE_PARM_DESC(preserve_state, "Keep current selector levels when binding on a running system");

static ssize_t v50_read(struct device *dev, struct gpio_desc *gpio, char *buf)
{
	int value = gpiod_get_value_cansleep(gpio);

	return value < 0 ? value : sysfs_emit(buf, "%d\n", value);
}

static ssize_t chip_select_show(struct device *dev,
			       struct device_attribute *attr, char *buf)
{
	struct v50_sim *sim = dev_get_drvdata(dev);

	return v50_read(dev, sim->chip, buf);
}

static ssize_t psim_select_show(struct device *dev,
			       struct device_attribute *attr, char *buf)
{
	struct v50_sim *sim = dev_get_drvdata(dev);

	return v50_read(dev, sim->psim, buf);
}

static ssize_t psim_present_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	struct v50_sim *sim = dev_get_drvdata(dev);

	return v50_read(dev, sim->detect, buf);
}

static ssize_t v50_write(struct device *dev, struct gpio_desc *gpio,
			 const char *buf, size_t count)
{
	struct v50_sim *sim = dev_get_drvdata(dev);
	unsigned int value;
	int ret;

	ret = kstrtouint(buf, 10, &value);
	if (ret || value > 1)
		return -EINVAL;
	mutex_lock(&sim->lock);
	ret = gpiod_get_value_cansleep(gpio);
	if (ret >= 0 && ret != value)
		ret = gpiod_direction_output(gpio, value);
	if (ret >= 0) {
		ret = gpiod_get_value_cansleep(gpio);
		if (ret >= 0)
			ret = ret == value ? 0 : -EIO;
	}
	mutex_unlock(&sim->lock);
	return ret < 0 ? ret : count;
}

static ssize_t chip_select_store(struct device *dev,
				struct device_attribute *attr,
				const char *buf, size_t count)
{
	struct v50_sim *sim = dev_get_drvdata(dev);

	return v50_write(dev, sim->chip, buf, count);
}

static ssize_t psim_select_store(struct device *dev,
				struct device_attribute *attr,
				const char *buf, size_t count)
{
	struct v50_sim *sim = dev_get_drvdata(dev);

	return v50_write(dev, sim->psim, buf, count);
}

static DEVICE_ATTR_RW(chip_select);
static DEVICE_ATTR_RW(psim_select);
static DEVICE_ATTR_RO(psim_present);
static struct attribute *v50_sim_attrs[] = {
	&dev_attr_chip_select.attr,
	&dev_attr_psim_select.attr,
	&dev_attr_psim_present.attr,
	NULL,
};
ATTRIBUTE_GROUPS(v50_sim);

static enum gpiod_flags v50_initial(const char *key, bool default_high)
{
	struct device_node *chosen;
	const char *args, *value;
	bool high = default_high;

	chosen = of_find_node_by_path("/chosen");
	if (chosen && !of_property_read_string(chosen, "bootargs", &args)) {
		value = strstr(args, key);
		if (value && (value == args || value[-1] == ' ')) {
			value += strlen(key);
			if ((value[0] == '0' || value[0] == '1') &&
			    (value[1] == '\0' || value[1] == ' '))
				high = value[0] == '1';
		}
	}
	of_node_put(chosen);
	return high ? GPIOD_OUT_HIGH : GPIOD_OUT_LOW;
}

static int v50_sim_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *v50;
	struct v50_sim *sim;
	int chip, psim, ret;

	/* Some generic vendor trees carry unused SIM nodes on other products. */
	v50 = of_find_compatible_node(NULL, NULL, "awinic,aw9523b");
	if (!v50)
		return -ENODEV;
	of_node_put(v50);
	sim = devm_kzalloc(dev, sizeof(*sim), GFP_KERNEL);
	if (!sim)
		return -ENOMEM;
	mutex_init(&sim->lock);
	/* The stock binding spells these properties with a singular -gpio. */
	sim->detect = devm_gpiod_get(dev, "esim1-psim-switch", GPIOD_IN);
	if (IS_ERR(sim->detect))
		return dev_err_probe(dev, PTR_ERR(sim->detect), "card detect GPIO\n");
	sim->chip = devm_gpiod_get(dev, "esim2-esim3-switch",
				 preserve_state ? GPIOD_ASIS :
				 v50_initial("androidboot.simswitch=", true));
	if (IS_ERR(sim->chip))
		return dev_err_probe(dev, PTR_ERR(sim->chip), "eSIM selector GPIO\n");
	sim->psim = devm_gpiod_get(dev, "soft-psim-switch",
				 preserve_state ? GPIOD_ASIS :
				 v50_initial("androidboot.psimswitch=", false));
	if (IS_ERR(sim->psim))
		return dev_err_probe(dev, PTR_ERR(sim->psim), "physical SIM selector GPIO\n");
	if (preserve_state) {
		/* LK may have left an unused selector as an input with a pull-down.
		 * Retain its actual level, but take output ownership for later writes. */
		chip = gpiod_get_value_cansleep(sim->chip);
		psim = gpiod_get_value_cansleep(sim->psim);
		if (chip < 0 || psim < 0)
			return dev_err_probe(dev, chip < 0 ? chip : psim, "read selectors\n");
		ret = gpiod_direction_output(sim->chip, chip);
		if (!ret)
			ret = gpiod_direction_output(sim->psim, psim);
		if (ret)
			return dev_err_probe(dev, ret, "preserve selector outputs\n");
	}
	platform_set_drvdata(pdev, sim);
	return 0;
}

static const struct of_device_id v50_sim_match[] = {
	{ .compatible = "zte,sim_gpio_ctrl" },
	{ }
};
MODULE_DEVICE_TABLE(of, v50_sim_match);

static struct platform_driver v50_sim_driver = {
	.probe = v50_sim_probe,
	.driver = {
		.name = "zte-v50-sim",
		.of_match_table = v50_sim_match,
		.dev_groups = v50_sim_groups,
	},
};
module_platform_driver(v50_sim_driver);
MODULE_DESCRIPTION("ZTE V50 SIM multiplexer using the stock DT binding");
MODULE_LICENSE("GPL");
