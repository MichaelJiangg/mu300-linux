/* SPDX-License-Identifier: GPL-2.0 */
/* Unisoc SoC ID registers (upstream/port/drivers/soc/sprd/sprd_soc_id.c), as in the Unisoc 5.4 kernel */
#ifndef __SPRD_SOC_ID_DRV_H__
#define __SPRD_SOC_ID_DRV_H__

#include <linux/types.h>

typedef enum {
	AON_CHIP_ID = 0,
	AON_PLAT_ID,
	AON_IMPL_ID,
	AON_MFT_ID,
	AON_VER_ID,
} sprd_soc_id_type_t;

int sprd_get_soc_id(sprd_soc_id_type_t soc_id_type, u32 *id, int id_len);

#endif
