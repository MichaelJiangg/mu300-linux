/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_POWER_UMP9620_BATTERY_H
#define _LINUX_POWER_UMP9620_BATTERY_H

#include <linux/of.h>

/* The shared F50 DT also carries charger/FGU/PD nodes, without a battery.
 * Only the battery board enables the stock charger policy service. Check it
 * before any register access; a responding charger address is insufficient.
 */
static inline bool ump9620_has_battery_policy(void)
{
	struct device_node *policy = of_find_node_by_path("/charger_policy_service");
	bool enabled = policy && of_device_is_available(policy);

	of_node_put(policy);
	return enabled;
}

#endif
