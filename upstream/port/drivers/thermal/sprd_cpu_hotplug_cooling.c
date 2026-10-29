// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc CPU hotplug cooling: the cooling devices thermal-cpu-0, -1 and -2 of the vendor device tree's
 * /cooling-devices/cluster{0,1,2}-cooling, which take a cluster's cores offline when it is hot and bring them back
 * when it cools.
 *
 * From the Unisoc 5.4 kernel's sprd_cpu_cooling (drivers/thermal/sprd_cpu_cooling.c): the same devices, names, OF
 * nodes and core order (the highest core of a cluster goes first, cpu0 never). The 5.4 driver gives the power
 * allocator a power model and only takes cores away once the cluster's frequency is down to sprd,min-cpufreq and the
 * zone is at sprd,max-temp, never below sprd,min-cpunum cores. Mainline's soc-thmzone (mu300_thermal) runs step_wise,
 * which asks for a state directly, so the device tree's limits are applied here instead: the state goes no higher
 * than the cores a cluster may lose, and a higher state takes a core away only while the cluster's frequency limit is
 * at or under sprd,min-cpufreq (cpufreq cooling at the same trip has done what it can); the temperature limit is the
 * trip the zone binds it at (85 C; sprd,max-temp is 85 C for the A76 clusters and 90 C for the A55s). A lower state
 * brings cores back at once. The thermal core binds them to the zone
 * through the device tree's cooling maps (soc-thmzone, from its 85 C trip), as on 5.4.
 */
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/cpumask.h>
#include <linux/err.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/thermal.h>
#include <linux/topology.h>
#include <linux/version.h>

struct sprd_hp_cdev {
	struct thermal_cooling_device *cdev;
	struct cpumask cpus;		/* the cluster's cores */
	struct cpumask off;		/* the ones this driver took offline */
	unsigned int max_state;		/* cores it may take: all but sprd,min-cpunum, never cpu0 */
	unsigned int state;
	u32 min_freq;			/* kHz: sprd,min-cpufreq */
	struct mutex lock;
};

static struct sprd_hp_cdev *hp_cdevs[3];

static int sprd_hp_get_max_state(struct thermal_cooling_device *cdev, unsigned long *state)
{
	struct sprd_hp_cdev *hp = cdev->devdata;

	*state = hp->max_state;
	return 0;
}

static int sprd_hp_get_cur_state(struct thermal_cooling_device *cdev, unsigned long *state)
{
	struct sprd_hp_cdev *hp = cdev->devdata;

	*state = hp->state;
	return 0;
}

/*
 * may a core go: the cluster held at its minimum frequency (5.4's power2state rule). The zone's temperature is not
 * read here: the thermal core calls this with the zone locked, and it only calls it above the trip it is bound at.
 */
static bool sprd_hp_may_take(struct sprd_hp_cdev *hp)
{
	struct cpufreq_policy *policy;
	unsigned int max = UINT_MAX;

	policy = cpufreq_cpu_get(cpumask_first(&hp->cpus));
	if (policy) {
		max = policy->max;
		cpufreq_cpu_put(policy);
	}
	return max <= hp->min_freq;
}

static int sprd_hp_set_cur_state(struct thermal_cooling_device *cdev, unsigned long state)
{
	struct sprd_hp_cdev *hp = cdev->devdata;
	int cpu, ret = 0;

	if (state > hp->max_state)
		return -EINVAL;
	mutex_lock(&hp->lock);
	/* up: the highest cores first, never cpu0; one core per call, and only under 5.4's conditions */
	if (state > hp->state && sprd_hp_may_take(hp)) {
		for (cpu = nr_cpu_ids - 1; cpu > 0; cpu--) {
			if (!cpumask_test_cpu(cpu, &hp->cpus) || cpumask_test_cpu(cpu, &hp->off) || !cpu_online(cpu))
				continue;
			ret = remove_cpu(cpu);
			if (!ret) {
				cpumask_set_cpu(cpu, &hp->off);
				hp->state++;
				pr_info("thermal-cpu: cpu%d offline (cooling state %u)\n", cpu, hp->state);
			}
			break;
		}
	}
	/* down: the cores back, the lowest first */
	while (state < hp->state) {
		cpu = cpumask_first(&hp->off);
		if (cpu >= nr_cpu_ids)
			break;
		/* (one brought back by hand meanwhile counts as back) */
		ret = cpu_online(cpu) ? 0 : add_cpu(cpu);
		if (ret) {
			pr_warn("thermal-cpu: cpu%d did not come back: %d\n", cpu, ret);
			break;
		}
		cpumask_clear_cpu(cpu, &hp->off);
		hp->state--;
		pr_info("thermal-cpu: cpu%d online (cooling state %u)\n", cpu, hp->state);
	}
	mutex_unlock(&hp->lock);
	return 0;
}

static const struct thermal_cooling_device_ops sprd_hp_ops = {
	.get_max_state = sprd_hp_get_max_state,
	.get_cur_state = sprd_hp_get_cur_state,
	.set_cur_state = sprd_hp_set_cur_state,
};

static void sprd_hp_destroy(void)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(hp_cdevs); i++) {
		struct sprd_hp_cdev *hp = hp_cdevs[i];

		if (!hp)
			continue;
		sprd_hp_set_cur_state(hp->cdev, 0);	/* every core back */
		thermal_cooling_device_unregister(hp->cdev);
		kfree(hp);
		hp_cdevs[i] = NULL;
	}
}

static int __init sprd_hp_init(void)
{
	struct device_node *np;
	int n = 0;

	np = of_find_node_by_path("/cooling-devices");
	if (!np)
		return -ENODEV;
	for_each_available_child_of_node_scoped(np, child) {
		struct sprd_hp_cdev *hp;
		char name[THERMAL_NAME_LENGTH];
		u32 min_cpus = 0;
		int id, cpu;

		id = of_alias_get_id(child, "cooling-device");
		if (id < 0 || id >= ARRAY_SIZE(hp_cdevs) || hp_cdevs[id])
			continue;
		hp = kzalloc(sizeof(*hp), GFP_KERNEL);
		if (!hp)
			break;
		mutex_init(&hp->lock);
		for_each_possible_cpu(cpu)
			if (topology_cluster_id(cpu) == id)
				cpumask_set_cpu(cpu, &hp->cpus);
		of_property_read_u32(child, "sprd,min-cpunum", &min_cpus);
		of_property_read_u32(child, "sprd,min-cpufreq", &hp->min_freq);
		if (cpumask_test_cpu(0, &hp->cpus) && min_cpus < 1)
			min_cpus = 1;
		hp->max_state = cpumask_weight(&hp->cpus) > min_cpus ? cpumask_weight(&hp->cpus) - min_cpus : 0;
		snprintf(name, sizeof(name), "thermal-cpu-%d", id);
#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)
		/* 7.2: an id for the new three-cell cooling specifier; the vendor tree's two-cell maps ignore it */
		hp->cdev = thermal_of_cooling_device_register(child, 0, name, hp, &sprd_hp_ops);
#else
		hp->cdev = thermal_of_cooling_device_register(child, name, hp, &sprd_hp_ops);
#endif
		if (IS_ERR(hp->cdev)) {
			pr_warn("%s: cannot register: %ld\n", name, PTR_ERR(hp->cdev));
			kfree(hp);
			continue;
		}
		hp_cdevs[id] = hp;
		n++;
		pr_info("%s: cores %*pbl, may take %u (at %u kHz or less)\n", name, cpumask_pr_args(&hp->cpus),
			hp->max_state, hp->min_freq);
	}
	of_node_put(np);
	return n ? 0 : -ENODEV;
}
module_init(sprd_hp_init);

static void __exit sprd_hp_exit(void)
{
	sprd_hp_destroy();
}
module_exit(sprd_hp_exit);

MODULE_DESCRIPTION("Unisoc CPU hotplug cooling (thermal-cpu-N)");
MODULE_LICENSE("GPL");
