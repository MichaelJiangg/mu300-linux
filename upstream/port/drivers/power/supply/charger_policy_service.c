// SPDX-License-Identifier: GPL-2.0
/*
 * ZTE's charge policy for the U30 Air ("zte,charger-policy-service"), and the battery cooling device of the 5.4
 * charger-manager.
 *
 * The expired mode, from ZTE's 5.4 kernel (drivers/vendor/common/power/charger_policy_service.c): a device that has
 * been on its charger for policy,timeout-seconds (57600 s, 16 hours, on the U30 Air) without a break keeps its battery
 * between policy,expired-min-capacity and policy,expired-max-capacity (70 and 90 %) instead of at 100 %: charging
 * stops once the battery reaches the middle (80 %) and starts again when it is down to the minimum; unplugging starts
 * the 16 hours again. As on 5.4 it rests while the battery is at 15.0 C or colder (policy,low-temp-enable), and it
 * looks every 30 s and at every change of the battery or the charger. What it does differently: ZTE's switched the
 * charger's input off as well above the maximum (its power path ran the device from the battery); mainline's
 * bq256xx has no input switch, so here charging is only paused (charge_type N/A, Fast to resume, as mu300-power
 * does it), which holds the battery where it is with the device on the charger. ZTE's demo mode, its 30-day forced
 * discharge and the zte_misc controls are left out; the state is in /sys/module/charger_policy_service/parameters.
 *
 * The cooling device "battery" (5.4: charger-manager's "battery" supply, which the thermal HAL limited): four
 * states, 0 the charger's own charge current, 1 to 3 three quarters, a half and a quarter of it. No thermal zone of
 * the device tree uses it (none did on 5.4); thermal-guard or a zone bound by hand can.
 */
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/thermal.h>
#include <linux/timekeeping.h>
#include <linux/workqueue.h>

#define POLICY_CHARGER		"bq256xx-charger"
#define POLICY_BATTERY		"sc27xx-fgu"
#define POLICY_INTERVAL_S	30
#define POLICY_LOWTEMP		150	/* 0.1 C, as the vendor's CHARGING_POLICY_LOWTEMP_THRESHOLD */
#define BATT_COOL_STATES	3

enum policy_state { POLICY_IDLE, POLICY_CHARGING, POLICY_HOLDING };
static const char * const policy_state_names[] = { "idle", "charging", "holding" };

struct charger_policy {
	struct device *dev;
	struct mutex lock;
	struct notifier_block nb;
	struct delayed_work work;
	bool expired_mode, low_temp;
	u32 timeout_s;
	int cap_min, cap_max;
	enum policy_state state;
	time64_t plugged_since;		/* boot time of the plug-in, 0 unplugged */
	bool paused;			/* this driver set charge_type N/A */
	struct thermal_cooling_device *cdev;
	unsigned long cool_state;
	int ichg_saved;			/* uA, the charger's current before the cooling device lowered it */
};

static struct charger_policy *policy;

/* the time on the charger before the expired mode, in seconds; -1: the device tree's (policy,timeout-seconds) */
static int timeout_seconds = -1;
module_param(timeout_seconds, int, 0644);
MODULE_PARM_DESC(timeout_seconds, "seconds on the charger before the battery is kept in its window (-1: the device tree's)");

static int policy_get(const char *name, enum power_supply_property psp, int *val)
{
	union power_supply_propval v;
	struct power_supply *psy = power_supply_get_by_name(name);
	int ret;

	if (!psy)
		return -ENODEV;
	ret = power_supply_get_property(psy, psp, &v);
	power_supply_put(psy);
	/* (bq256xx returns the value it read, not 0: only a negative return is an error) */
	if (ret < 0)
		return ret;
	*val = v.intval;
	return 0;
}

static int policy_set(const char *name, enum power_supply_property psp, int val)
{
	union power_supply_propval v = { .intval = val };
	struct power_supply *psy = power_supply_get_by_name(name);
	int ret;

	if (!psy)
		return -ENODEV;
	ret = power_supply_set_property(psy, psp, &v);
	power_supply_put(psy);
	return ret < 0 ? ret : 0;
}

static bool policy_psy_there(const char *name)
{
	struct power_supply *psy = power_supply_get_by_name(name);

	if (psy)
		power_supply_put(psy);
	return psy;
}

static void policy_charging(struct charger_policy *p, bool on)
{
	if (on == !p->paused)
		return;
	if (policy_set(POLICY_CHARGER, POWER_SUPPLY_PROP_CHARGE_TYPE,
		       on ? POWER_SUPPLY_CHARGE_TYPE_FAST : POWER_SUPPLY_CHARGE_TYPE_NONE)) {
		dev_warn_ratelimited(p->dev, "cannot switch charging %s\n", on ? "on" : "off");
		return;
	}
	p->paused = !on;
	dev_info(p->dev, "charging %s\n", on ? "on again" : "paused (expired mode)");
}

static void policy_step(struct charger_policy *p)
{
	int online = 0, cap = -1, temp = 1000;
	time64_t now = ktime_get_boottime_seconds();

	policy_get(POLICY_CHARGER, POWER_SUPPLY_PROP_ONLINE, &online);
	policy_get(POLICY_BATTERY, POWER_SUPPLY_PROP_CAPACITY, &cap);
	policy_get(POLICY_BATTERY, POWER_SUPPLY_PROP_TEMP, &temp);

	/* off, unplugged or cold: back to normal charging, the 16 hours start again at the next plug-in */
	if (!p->expired_mode || !online || (p->low_temp && temp <= POLICY_LOWTEMP) || cap < 0) {
		if (p->state != POLICY_IDLE)
			dev_info(p->dev, "expired mode left (%s)\n", !online ? "unplugged" : "off, cold or no capacity");
		policy_charging(p, true);
		p->state = POLICY_IDLE;
		p->plugged_since = online ? (p->plugged_since ?: now) : 0;
		return;
	}
	if (!p->plugged_since)
		p->plugged_since = now;

	switch (p->state) {
	case POLICY_IDLE:
		if (now - p->plugged_since < (READ_ONCE(timeout_seconds) >= 0 ? READ_ONCE(timeout_seconds) : p->timeout_s))
			break;
		dev_info(p->dev, "on the charger for %lld s: expired mode, battery kept at %d-%d %%\n",
			 now - p->plugged_since, p->cap_min, p->cap_max);
		p->state = POLICY_CHARGING;
		fallthrough;
	case POLICY_CHARGING:
		policy_charging(p, true);
		/* the vendor's power-path rule: stop at the middle of the window */
		if (cap >= (p->cap_min + p->cap_max) / 2) {
			p->state = POLICY_HOLDING;
			policy_charging(p, false);
		}
		break;
	case POLICY_HOLDING:
		policy_charging(p, false);
		if (cap <= p->cap_min) {
			p->state = POLICY_CHARGING;
			policy_charging(p, true);
		}
		break;
	}
}

static void policy_work(struct work_struct *work)
{
	struct charger_policy *p = container_of(to_delayed_work(work), struct charger_policy, work);

	mutex_lock(&p->lock);
	policy_step(p);
	mutex_unlock(&p->lock);
	/* the next look in 30 s (the vendor's alarm timer: a work item here, which a system sleep pauses) */
	mod_delayed_work(system_freezable_wq, &p->work, secs_to_jiffies(POLICY_INTERVAL_S));
}

static int policy_psy_changed(struct notifier_block *nb, unsigned long event, void *data)
{
	struct charger_policy *p = container_of(nb, struct charger_policy, nb);
	struct power_supply *psy = data;

	if (event == PSY_EVENT_PROP_CHANGED &&
	    (!strcmp(psy->desc->name, POLICY_BATTERY) || !strcmp(psy->desc->name, POLICY_CHARGER)))
		mod_delayed_work(system_freezable_wq, &p->work, msecs_to_jiffies(200));
	return NOTIFY_OK;
}

/* the battery cooling device */
static int batt_cool_get_max(struct thermal_cooling_device *cdev, unsigned long *state)
{
	*state = BATT_COOL_STATES;
	return 0;
}

static int batt_cool_get_cur(struct thermal_cooling_device *cdev, unsigned long *state)
{
	struct charger_policy *p = cdev->devdata;

	*state = p->cool_state;
	return 0;
}

static int batt_cool_set_cur(struct thermal_cooling_device *cdev, unsigned long state)
{
	struct charger_policy *p = cdev->devdata;
	int ret = 0, cur;

	if (state > BATT_COOL_STATES)
		return -EINVAL;
	mutex_lock(&p->lock);
	if (state == p->cool_state)
		goto out;
	if (!p->cool_state) {
		/* the charger's own current, to go back to */
		ret = policy_get(POLICY_CHARGER, POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT, &cur);
		if (ret)
			goto out;
		p->ichg_saved = cur;
	}
	cur = p->ichg_saved / (BATT_COOL_STATES + 1) * (BATT_COOL_STATES + 1 - state);
	ret = policy_set(POLICY_CHARGER, POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT, state ? cur : p->ichg_saved);
	if (!ret) {
		p->cool_state = state;
		dev_info(p->dev, "battery cooling state %lu: charge current %d uA\n", state,
			 state ? cur : p->ichg_saved);
	}
out:
	mutex_unlock(&p->lock);
	return ret;
}

static const struct thermal_cooling_device_ops batt_cool_ops = {
	.get_max_state = batt_cool_get_max,
	.get_cur_state = batt_cool_get_cur,
	.set_cur_state = batt_cool_set_cur,
};

static int param_state_get(char *buf, const struct kernel_param *kp)
{
	struct charger_policy *p = READ_ONCE(policy);

	if (!p)
		return sysfs_emit(buf, "none\n");
	return sysfs_emit(buf, "%s%s, on the charger %lld s\n", policy_state_names[p->state],
			  p->paused ? " (charging paused)" : "",
			  p->plugged_since ? ktime_get_boottime_seconds() - p->plugged_since : 0LL);
}
static const struct kernel_param_ops param_state_ops = { .get = param_state_get };
module_param_cb(state, &param_state_ops, NULL, 0444);
MODULE_PARM_DESC(state, "the expired mode's state");

static void policy_stop(void *data)
{
	struct charger_policy *p = data;

	power_supply_unreg_notifier(&p->nb);
	cancel_delayed_work_sync(&p->work);
	WRITE_ONCE(policy, NULL);
	mutex_lock(&p->lock);
	policy_charging(p, true);		/* nothing left paused by this driver */
	mutex_unlock(&p->lock);
}

static void batt_cool_stop(void *data)
{
	struct charger_policy *p = data;

	batt_cool_set_cur(p->cdev, 0);		/* the charger's own current back */
	thermal_cooling_device_unregister(p->cdev);
}

static int charger_policy_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct charger_policy *p;
	u32 v;
	int ret;

	if (!policy_psy_there(POLICY_CHARGER) || !policy_psy_there(POLICY_BATTERY))
		return dev_err_probe(dev, -EPROBE_DEFER, "the charger and the fuel gauge\n");

	p = devm_kzalloc(dev, sizeof(*p), GFP_KERNEL);
	if (!p)
		return -ENOMEM;
	p->dev = dev;
	mutex_init(&p->lock);
	p->expired_mode = !of_property_read_u32(np, "policy,enable", &v) && v &&
			  (of_property_read_u32(np, "policy,expired-mode-enable", &v) || v);
	p->low_temp = !of_property_read_u32(np, "policy,low-temp-enable", &v) && v;
	p->timeout_s = 86400;
	of_property_read_u32(np, "policy,timeout-seconds", &p->timeout_s);
	p->cap_max = 70;
	p->cap_min = 50;
	if (!of_property_read_u32(np, "policy,expired-max-capacity", &v))
		p->cap_max = v;
	if (!of_property_read_u32(np, "policy,expired-min-capacity", &v))
		p->cap_min = v;
	if (p->cap_min < 1 || p->cap_max > 100 || p->cap_min >= p->cap_max)
		return dev_err_probe(dev, -EINVAL, "capacity window %d-%d\n", p->cap_min, p->cap_max);

	INIT_DELAYED_WORK(&p->work, policy_work);
	p->nb.notifier_call = policy_psy_changed;
	ret = power_supply_reg_notifier(&p->nb);
	if (ret)
		return ret;
	WRITE_ONCE(policy, p);
	ret = devm_add_action_or_reset(dev, policy_stop, p);
	if (ret)
		return ret;
	mod_delayed_work(system_freezable_wq, &p->work, 0);

	p->cdev = thermal_cooling_device_register("battery", p, &batt_cool_ops);
	if (IS_ERR(p->cdev))
		return dev_err_probe(dev, PTR_ERR(p->cdev), "battery cooling device\n");
	ret = devm_add_action_or_reset(dev, batt_cool_stop, p);
	if (ret)
		return ret;

	dev_info(dev, "expired mode %s: after %u s on the charger, battery kept at %d-%d %%\n",
		 p->expired_mode ? "on" : "off", p->timeout_s, p->cap_min, p->cap_max);
	return 0;
}

static const struct of_device_id charger_policy_match[] = {
	{ .compatible = "zte,charger-policy-service" },
	{ }
};
MODULE_DEVICE_TABLE(of, charger_policy_match);

static struct platform_driver charger_policy_driver = {
	.driver = {
		.name = "zte,charger-policy-service",
		.of_match_table = charger_policy_match,
	},
	.probe = charger_policy_probe,
};
module_platform_driver(charger_policy_driver);

MODULE_DESCRIPTION("ZTE charge policy (expired mode) and battery cooling device");
MODULE_LICENSE("GPL");
