// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc UMP9620 (SC27xx family) USB Type-C detection: the PMIC's Type-C block (typec@380, "sprd,ump96xx-typec").
 *
 * Ported from the Unisoc/ZTE 5.4 kernel (drivers/usb/typec/sc27xx_typec.c), detection only, as 5.4 runs it on the
 * F50: the block runs its own attach/detach state machine in the mode the device tree gives (sprd,mode: DRP on these
 * boards), with the CC trims from the PMIC's eFuse, and this driver reports what it finds - a Type-C port (port0) with
 * a partner while something is attached, its power and data role from the attach state (sink/device or
 * source/host), an extcon device (USB, USB_HOST and JACK_HEADPHONE as 5.4's; its SOURCE and SINK cables are Unisoc's
 * own, mainline has none, and 5.4 set them only for the PD stack) and the CC pin in use
 * (typec_cc_polarity_role). It switches no role itself and moves no lane: what drives VBUS and the USB controller's
 * role on mainline (extcon-usb-gpio, mu300-usb, patch 0007) and the USB 3 lanes (the PHY) are not its business; no
 * mainline driver takes its extcon. Writing a role in the Type-C class is refused (no ops), as on 5.4.
 *
 * The U30 Air's device tree marks the block use_pdhub_c2c: on 5.4 Unisoc's PD stack (sprd_tcpm) had the port there.
 * Mainline's equivalent, ump9620_tcpc (patch 0020), is off unless asked for (mu300-usb pd on), so this driver has
 * the port by default there too. When the port controller is enabled, mu300-usb unbinds this driver before it loads
 * it and binds it again when it goes; and this driver does not bind while the port controller has the block.
 *
 * Left out of the vendor driver: the PD stack's hooks (swap events, interrupt clearing during a swap), ZTE's
 * try-role option and exception logging, the SC2721/UMP518 variants.
 */
#include <linux/extcon-provider.h>
#include <linux/interrupt.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/nvmem-consumer.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/random.h>
#include <linux/regmap.h>
#include <linux/slab.h>
#include <linux/usb/typec.h>

/* registers of the Type-C block */
#define SC27XX_EN			0x00
#define SC27XX_MODE			0x04
#define SC27XX_INT_EN			0x0c
#define SC27XX_INT_CLR			0x10
#define SC27XX_INT_RAW			0x14
#define SC27XX_INT_MASK			0x18
#define SC27XX_STATUS			0x1c
#define SC27XX_TCCDE_CNT		0x20
#define SC27XX_RTRIM			0x3c
#define SC2730_TDRP_CNT			0x48
#define SC2730_DBG1			0x60

#define SC27XX_TYPEC_USB20_ONLY		BIT(4)
#define SC27XX_MODE_SNK			0
#define SC27XX_MODE_SRC			1
#define SC27XX_MODE_DRP			2
#define SC27XX_MODE_MASK		3
#define SC27XX_RP_330UA			(BIT(2) | BIT(3))
#define SC27XX_ATTACH_INT		BIT(0)
#define SC27XX_DETACH_INT		BIT(1)
#define SC27XX_STATE_MASK		GENMASK(4, 0)
#define SC27XX_EVENT_MASK		GENMASK(9, 0)
#define SC2730_CC_MASK			GENMASK(7, 0)
#define CC1_DFP_CHECK			BIT(7)
#define CC2_DFP_CHECK			BIT(3)
#define CC1_UFP_CON			BIT(0)

/* the CC detection's debounce, 100 ms (Unisoc: PD signalling at 150 ms disturbed it) */
#define SC27XX_TCC_DEBOUNCE_CNT		0xc7f
/* the DRP toggle period, 50 to 100 ms at random after a detach (two devices restarted together, Unisoc) */
#define SC27XX_MIN_TDRP_CNT		0x63f
#define SC27XX_TDRP_RANGE		0x640

/* the UMP9620's Type-C current trim from the eFuse */
#define UMP9620_RESERVERED_CORE		0x234c
#define TRIM_CURRENT_FROMEFUSE		BIT(4)
#define UMP9620_EFUSE_CC1_SHIFT		1
#define UMP9620_EFUSE_CC2_SHIFT		11
#define SC27XX_CC_MASK(n)		GENMASK((n) + 4, (n))

enum sc27xx_typec_state {
	SC27XX_DETACHED_SNK,
	SC27XX_ATTACHWAIT_SNK,
	SC27XX_ATTACHED_SNK,
	SC27XX_DETACHED_SRC,
	SC27XX_ATTACHWAIT_SRC,
	SC27XX_ATTACHED_SRC,
	SC27XX_POWERED_CABLE,
	SC27XX_AUDIO_CABLE,
	SC27XX_DEBUG_CABLE,
	SC27XX_TOGGLE_SLEEP,
	SC27XX_ERR_RECOV,
	SC27XX_DISABLED,
};

enum sc27xx_cc_polarity { SC27XX_CC1, SC27XX_CC2 };

static const char * const sc27xx_cc_names[] = { "cc_1", "cc_2" };

static const unsigned int sc27xx_typec_cable[] = {
	EXTCON_USB,
	EXTCON_USB_HOST,
	EXTCON_JACK_HEADPHONE,
	EXTCON_NONE,
};

struct sc27xx_typec {
	struct device *dev;
	struct regmap *regmap;
	u32 base;
	int irq;
	int mode;
	bool usb20_only;
	bool use_pdhub_c2c;
	struct extcon_dev *edev;
	struct typec_port *port;
	struct typec_partner *partner;
	struct typec_capability cap;
	struct mutex lock;
	u32 state;
	u32 pre_state;
	enum sc27xx_cc_polarity cc;
};

static void sc27xx_typec_set_cc(struct sc27xx_typec *sc)
{
	enum sc27xx_cc_polarity cc;
	u32 val;

	if (regmap_read(sc->regmap, sc->base + SC2730_DBG1, &val))
		return;
	val &= SC2730_CC_MASK;
	if (val & (CC1_DFP_CHECK | CC2_DFP_CHECK))
		cc = (val & CC1_DFP_CHECK) ? SC27XX_CC1 : SC27XX_CC2;	/* we are the source */
	else
		cc = (val & CC1_UFP_CON) ? SC27XX_CC1 : SC27XX_CC2;	/* we are the sink */
	if (cc == sc->cc)
		return;
	sc->cc = cc;
	sysfs_notify(&sc->dev->kobj, NULL, "typec_cc_polarity_role");
	kobject_uevent(&sc->dev->kobj, KOBJ_CHANGE);
}

static void sc27xx_typec_connect(struct sc27xx_typec *sc)
{
	enum typec_role power_role, vconn_role;
	enum typec_data_role data_role;
	struct typec_partner_desc desc = { .accessory = TYPEC_ACCESSORY_NONE };
	struct typec_partner *partner;

	if (sc->partner)
		return;
	switch (sc->state) {
	case SC27XX_ATTACHED_SNK:
	case SC27XX_DEBUG_CABLE:
		power_role = TYPEC_SINK;
		data_role = TYPEC_DEVICE;
		vconn_role = TYPEC_SINK;
		break;
	case SC27XX_ATTACHED_SRC:
	case SC27XX_AUDIO_CABLE:
		power_role = TYPEC_SOURCE;
		data_role = TYPEC_HOST;
		vconn_role = TYPEC_SOURCE;
		if (sc->state == SC27XX_AUDIO_CABLE)
			desc.accessory = TYPEC_ACCESSORY_AUDIO;
		break;
	default:
		/* the PMIC may report an attach in a state that is none (Unisoc: "workaround error status") */
		dev_dbg(sc->dev, "attach in state %u\n", sc->state);
		return;
	}

	partner = typec_register_partner(sc->port, &desc);
	if (IS_ERR(partner)) {
		dev_warn(sc->dev, "cannot register the partner: %ld\n", PTR_ERR(partner));
		return;
	}
	sc->partner = partner;
	if (sc->state != SC27XX_AUDIO_CABLE) {
		typec_set_pwr_opmode(sc->port, TYPEC_PWR_MODE_USB);
		typec_set_pwr_role(sc->port, power_role);
		typec_set_data_role(sc->port, data_role);
		typec_set_vconn_role(sc->port, vconn_role);
	}

	switch (sc->state) {
	case SC27XX_ATTACHED_SNK:
	case SC27XX_DEBUG_CABLE:
		sc->pre_state = SC27XX_ATTACHED_SNK;
		extcon_set_state_sync(sc->edev, EXTCON_USB, true);
		break;
	case SC27XX_ATTACHED_SRC:
		sc->pre_state = SC27XX_ATTACHED_SRC;
		extcon_set_state_sync(sc->edev, EXTCON_USB_HOST, true);
		break;
	default:
		sc->pre_state = SC27XX_AUDIO_CABLE;
		extcon_set_state_sync(sc->edev, EXTCON_JACK_HEADPHONE, true);
		break;
	}
	sc27xx_typec_set_cc(sc);
	dev_info(sc->dev, "attached: %s\n", sc->state == SC27XX_AUDIO_CABLE ? "audio accessory" :
		 power_role == TYPEC_SINK ? "sink, device" : "source, host");
}

static void sc27xx_typec_disconnect(struct sc27xx_typec *sc)
{
	if (!sc->partner)
		return;
	typec_unregister_partner(sc->partner);
	sc->partner = NULL;
	typec_set_pwr_opmode(sc->port, TYPEC_PWR_MODE_USB);
	typec_set_pwr_role(sc->port, TYPEC_SINK);
	typec_set_data_role(sc->port, TYPEC_DEVICE);
	typec_set_vconn_role(sc->port, TYPEC_SINK);

	switch (sc->pre_state) {
	case SC27XX_ATTACHED_SNK:
		extcon_set_state_sync(sc->edev, EXTCON_USB, false);
		break;
	case SC27XX_ATTACHED_SRC:
		extcon_set_state_sync(sc->edev, EXTCON_USB_HOST, false);
		break;
	case SC27XX_AUDIO_CABLE:
		extcon_set_state_sync(sc->edev, EXTCON_JACK_HEADPHONE, false);
		break;
	}
	sc->pre_state = SC27XX_DETACHED_SNK;
	dev_info(sc->dev, "detached\n");
}

static void sc27xx_typec_random_tdrp(struct sc27xx_typec *sc)
{
	u32 rand = SC27XX_MIN_TDRP_CNT + (get_random_u32() & 0xfff) % SC27XX_TDRP_RANGE;

	regmap_write(sc->regmap, sc->base + SC2730_TDRP_CNT, rand);
}

static irqreturn_t sc27xx_typec_interrupt(int irq, void *data)
{
	struct sc27xx_typec *sc = data;
	u32 event, state;

	if (regmap_read(sc->regmap, sc->base + SC27XX_INT_MASK, &event))
		return IRQ_NONE;
	event &= SC27XX_EVENT_MASK;

	mutex_lock(&sc->lock);
	if (!regmap_read(sc->regmap, sc->base + SC27XX_STATUS, &state)) {
		sc->state = state & SC27XX_STATE_MASK;
		if (event & SC27XX_ATTACH_INT) {
			sc27xx_typec_connect(sc);
		} else if (event & SC27XX_DETACH_INT) {
			sc27xx_typec_disconnect(sc);
			sc27xx_typec_random_tdrp(sc);
		}
	}
	mutex_unlock(&sc->lock);

	regmap_write(sc->regmap, sc->base + SC27XX_INT_CLR, event);
	dev_dbg(sc->dev, "state %u, event 0x%x\n", sc->state, event);
	return IRQ_HANDLED;
}

/* the mode and Rp from the device tree, the debounce and the eFuse current trim, then the interrupts on */
static int sc27xx_typec_enable(struct sc27xx_typec *sc)
{
	u32 val;
	int ret;

	ret = regmap_read(sc->regmap, sc->base + SC27XX_MODE, &val);
	if (ret)
		return ret;
	val &= ~SC27XX_MODE_MASK;
	switch (sc->mode) {
	case TYPEC_PORT_SRC:
		val |= SC27XX_MODE_SRC;
		break;
	case TYPEC_PORT_SNK:
		val |= SC27XX_MODE_SNK;
		break;
	default:
		val |= SC27XX_MODE_DRP;
		break;
	}
	ret = regmap_write(sc->regmap, sc->base + SC27XX_MODE, val);
	if (ret)
		return ret;
	/* Rp current source level 330 uA */
	ret = regmap_write(sc->regmap, sc->base + SC27XX_MODE, val | SC27XX_RP_330UA);
	if (ret)
		return ret;
	/* USB 2.0 only: sink mode only, and not with the PD hub (as 5.4) */
	if (!sc->use_pdhub_c2c && sc->mode == TYPEC_PORT_SNK && sc->usb20_only) {
		ret = regmap_update_bits(sc->regmap, sc->base + SC27XX_EN, SC27XX_TYPEC_USB20_ONLY,
					 SC27XX_TYPEC_USB20_ONLY);
		if (ret)
			return ret;
	}
	ret = regmap_write(sc->regmap, sc->base + SC27XX_TCCDE_CNT, SC27XX_TCC_DEBOUNCE_CNT);
	if (ret)
		return ret;
	ret = regmap_update_bits(sc->regmap, UMP9620_RESERVERED_CORE, TRIM_CURRENT_FROMEFUSE,
				 TRIM_CURRENT_FROMEFUSE);
	if (ret)
		return ret;
	return regmap_update_bits(sc->regmap, sc->base + SC27XX_INT_EN, SC27XX_ATTACH_INT | SC27XX_DETACH_INT,
				  SC27XX_ATTACH_INT | SC27XX_DETACH_INT);
}

static int sc27xx_typec_efuse(struct sc27xx_typec *sc, const char *name, u32 shift, u32 *out)
{
	struct nvmem_cell *cell;
	u32 data = 0;
	size_t len;
	void *buf;

	cell = nvmem_cell_get(sc->dev, name);
	if (IS_ERR(cell))
		return PTR_ERR(cell);
	buf = nvmem_cell_read(cell, &len);
	nvmem_cell_put(cell);
	if (IS_ERR(buf))
		return PTR_ERR(buf);
	memcpy(&data, buf, min(len, sizeof(data)));
	kfree(buf);
	*out = (data & SC27XX_CC_MASK(shift)) >> shift;
	return 0;
}

static int sc27xx_typec_set_rtrim(struct sc27xx_typec *sc)
{
	u32 cc1, cc2;
	int ret;

	ret = sc27xx_typec_efuse(sc, "typec_cc1_cal", UMP9620_EFUSE_CC1_SHIFT, &cc1);
	if (!ret)
		ret = sc27xx_typec_efuse(sc, "typec_cc2_cal", UMP9620_EFUSE_CC2_SHIFT, &cc2);
	if (ret)
		return ret;
	return regmap_write(sc->regmap, sc->base + SC27XX_RTRIM, cc1 | cc2 << 5);
}

static ssize_t typec_cc_polarity_role_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct sc27xx_typec *sc = dev_get_drvdata(dev);

	return sysfs_emit(buf, "%s\n", sc27xx_cc_names[sc->cc]);
}
static DEVICE_ATTR_RO(typec_cc_polarity_role);

static struct attribute *sc27xx_typec_attrs[] = {
	&dev_attr_typec_cc_polarity_role.attr,
	NULL,
};
ATTRIBUTE_GROUPS(sc27xx_typec);

static void sc27xx_typec_unregister(void *data)
{
	struct sc27xx_typec *sc = data;

	/* the interrupt is gone (devm, registered later): no event can come in between */
	mutex_lock(&sc->lock);
	sc27xx_typec_disconnect(sc);
	mutex_unlock(&sc->lock);
	typec_unregister_port(sc->port);
}

static void sc27xx_typec_irq_off(void *data)
{
	struct sc27xx_typec *sc = data;

	regmap_update_bits(sc->regmap, sc->base + SC27XX_INT_EN, SC27XX_ATTACH_INT | SC27XX_DETACH_INT, 0);
}

/* the port controller (ump9620_tcpc, the PD block's driver) has the Type-C block: its interrupt and registers */
static bool sc27xx_typec_pd_bound(struct device *dev)
{
	struct device_node *pd = of_get_compatible_child(dev->parent->of_node, "sprd,ump9620-pd");
	struct platform_device *pdev = pd ? of_find_device_by_node(pd) : NULL;
	bool bound = false;

	of_node_put(pd);
	if (pdev) {
		bound = READ_ONCE(pdev->dev.driver);
		put_device(&pdev->dev);
	}
	return bound;
}

static int sc27xx_typec_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct sc27xx_typec *sc;
	u32 mode, state;
	int ret;

	if (sc27xx_typec_pd_bound(dev)) {
		dev_info(dev, "the USB-C port controller has the Type-C block (mu300-usb pd on): not bound\n");
		return -ENODEV;
	}

	sc = devm_kzalloc(dev, sizeof(*sc), GFP_KERNEL);
	if (!sc)
		return -ENOMEM;
	sc->dev = dev;
	mutex_init(&sc->lock);
	platform_set_drvdata(pdev, sc);

	sc->regmap = dev_get_regmap(dev->parent, NULL);
	if (!sc->regmap)
		return dev_err_probe(dev, -ENODEV, "no regmap\n");
	ret = of_property_read_u32(np, "reg", &sc->base);
	if (ret)
		return dev_err_probe(dev, ret, "no reg\n");
	ret = of_property_read_u32(np, "sprd,mode", &mode);
	if (ret)
		return dev_err_probe(dev, ret, "no sprd,mode\n");
	sc->irq = platform_get_irq(pdev, 0);
	if (sc->irq < 0)
		return sc->irq;
	sc->use_pdhub_c2c = of_property_read_bool(np, "use_pdhub_c2c");
	/* 5.4's reading of sprd,mode: 0 source, 2 dual role, anything else a USB 2.0-only sink */
	if (mode != TYPEC_PORT_SRC && mode != TYPEC_PORT_DRP) {
		mode = TYPEC_PORT_SNK;
		sc->usb20_only = true;
	}
	sc->mode = mode;

	sc->edev = devm_extcon_dev_allocate(dev, sc27xx_typec_cable);
	if (IS_ERR(sc->edev))
		return PTR_ERR(sc->edev);
	ret = devm_extcon_dev_register(dev, sc->edev);
	if (ret)
		return dev_err_probe(dev, ret, "cannot register the extcon device\n");

	sc->cap.type = mode;
	sc->cap.data = TYPEC_PORT_DRD;
	sc->cap.revision = USB_TYPEC_REV_1_2;
	sc->cap.prefer_role = TYPEC_NO_PREFERRED_ROLE;
	sc->port = typec_register_port(dev, &sc->cap);
	if (IS_ERR(sc->port))
		return dev_err_probe(dev, PTR_ERR(sc->port), "cannot register the port\n");
	ret = devm_add_action_or_reset(dev, sc27xx_typec_unregister, sc);
	if (ret)
		return ret;

	ret = sc27xx_typec_set_rtrim(sc);
	if (ret)
		return dev_err_probe(dev, ret, "cannot set the CC trims from the eFuse\n");

	ret = devm_request_threaded_irq(dev, sc->irq, NULL, sc27xx_typec_interrupt, IRQF_ONESHOT,
					dev_name(dev), sc);
	if (ret)
		return dev_err_probe(dev, ret, "cannot request the interrupt\n");
	ret = sc27xx_typec_enable(sc);
	if (ret)
		return dev_err_probe(dev, ret, "cannot set up the Type-C block\n");
	ret = devm_add_action_or_reset(dev, sc27xx_typec_irq_off, sc);
	if (ret)
		return ret;

	/* something attached before the driver came (the cable at boot): its attach interrupt may be long cleared */
	mutex_lock(&sc->lock);
	if (!regmap_read(sc->regmap, sc->base + SC27XX_STATUS, &state)) {
		sc->state = state & SC27XX_STATE_MASK;
		sc27xx_typec_connect(sc);
	}
	mutex_unlock(&sc->lock);
	return 0;
}

static const struct of_device_id sc27xx_typec_match[] = {
	{ .compatible = "sprd,ump96xx-typec" },
	{ }
};
MODULE_DEVICE_TABLE(of, sc27xx_typec_match);

static struct platform_driver sc27xx_typec_driver = {
	.probe = sc27xx_typec_probe,
	.driver = {
		.name = "sc27xx-typec",
		.of_match_table = sc27xx_typec_match,
		.dev_groups = sc27xx_typec_groups,
	},
};
module_platform_driver(sc27xx_typec_driver);

MODULE_DESCRIPTION("Unisoc UMP9620 USB Type-C detection");
MODULE_LICENSE("GPL");
