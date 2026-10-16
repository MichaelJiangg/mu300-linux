/* SPDX-License-Identifier: GPL-2.0
 * Copyright (C) 2019 Spreadtrum Communications Inc.
 * UMP9620 register definitions and calibration from the ZTE U30 Air GPL tree:
 * https://github.com/Enceka/android_kernel_zte_ums9620_mifi_u30air
 * drivers/usb/typec/tcpm/sc27xx_pd.c. Policy uses mainline TCPM.
 */
/* PMIC global registers definition */
#define SC27XX_MODULE_EN		0x1808
#define SC27XX_ARM_CLK_EN0		0x180c
#define SC27XX_RTC_CLK_EN0		0x1810
#define SC27XX_XTL_WAIT_CTRL0		0x1b78
#define UMP9620_MODULE_EN		0x2008
#define UMP9620_ARM_CLK_EN0		0x200c
#define UMP9620_RTC_CLK_EN0		0x2010
#define UMP9620_XTL_WAIT_CTRL0		0x2378
#define UMP518_MODULE_EN		0x1808
#define UMP518_ARM_CLK_EN0		0x180c
#define UMP518_RTC_CLK_EN0		0x1810
#define UMP518_XTL_WAIT_CTRL0		0x1b78
#define SC27XX_TYPEC_PD_EN		BIT(13)
#define SC27XX_CLK_PD_SEL		BIT(10)
#define SC27XX_CLK_PD_EN		BIT(9)
#define SC27XX_XTL_EN			BIT(8)

/* Typec controller registers definition */
#define SC27XX_TYPEC_EN			0x0
#define SC27XX_TYPEC_MODE		0x4
#define SC27XX_TYPEC_PD_CFG		0x8
#define SC27XX_TYPEC_STATUS		0x1c
#define SC27XX_TYPEC_SW_CFG		0x54
#define SC27XX_TYPEC_WC_REG		0x58
#define SC27XX_TYPEC_DBG1		0x60
#define SC27XX_TYPEC_IBIAS		0x70

#define SC27XX_TYPEC_RP_LEVEL(x)	(((x) << 2) & GENMASK(3, 2))
#define SC27XX_TYPEC_TRY_SRC_EN		BIT(7)
#define SC27XX_TYPEC_TRY_SINK_EN	BIT(8)

/* PD controller registers definition */
#define SC27XX_PD_TX_BUF		0x0
#define SC27XX_PD_RX_BUF		0x4
#define SC27XX_PD_HEAD_CFG		0x8
#define SC27XX_PD_CTRL			0xc
#define SC27XX_PD_CFG0			0x10
#define SC27XX_PD_CFG1			0x14
#define SC27XX_PD_MESG_ID_CFG		0x18
#define SC27XX_PD_STS0			0x1c
#define SC27XX_PD_STS1			0x20
#define SC27XX_INT_STS			0x24
#define SC27XX_INT_FLG			0x28
#define SC27XX_INT_CLR			0x2c
#define SC27XX_INT_EN			0x30
#define SC27XX_PD_PHY_CFG0		0x50
#define SC27XX_PD_PHY_CFG1		0x54
#define SC27XX_PD_PHY_CFG2		0x58

/* Bits definitions for SC27XX_TYPEC_PD_CFG register */
#define SC27XX_TYPEC_PD_SUPPORT		BIT(0)
#define SC27XX_TYPEC_PD_CONSTRACT	BIT(6)
#define SC27XX_TYPEC_PD_NO_CHEK_DETACH	BIT(9)
#define SC27XX_TYPEC_SW_FORCE_CC(x)	(((x) << 10) & GENMASK(11, 10))
#define SC27XX_TYPEC_VCCON_LDO_RDY	BIT(12)
#define SC27XX_TYPEC_VCCON_LDO_EN	BIT(13)

/* Bits definitions for SC27XX_TYPEC_STATUS register */
#define SC27XX_TYPEC_CURRENT_STATUS	GENMASK(4, 0)
#define SC27XX_TYPEC_FINAL_SWITCH	BIT(5)
#define SC27XX_TYPEC_VBUS_CL(x)		(((x) & GENMASK(7, 6)) >> 6)

/* Bits definitions for SC27XX_TYPEC_WC_REG register */
#define SC27XX_TYPEC_PD_PR_SWAP		BIT(2)
#define SC27XX_TYPEC_PD_VCONN_SWAP	BIT(1)

/* Bits definitions for SC27XX_TYPEC_DBG1 register */
#define SC27XX_TYPEC_VBUS_OK		BIT(8)
#define SC27XX_TYPEC_CONN_CC		BIT(9)

/* Bits definitions for SC27XX_TYPEC_IBIAS register */
#define SC27XX_TYPEC_RX_REF_DECREASE	BIT(7)

/* Bits definitions for SC27XX_PD_HEAD_CFG register */
#define SC27XX_PD_EXTHEAD		BIT(15)
#define SC27XX_PD_NUM_DO(x)		(((x) << 12) & GENMASK(14, 12))
#define SC27XX_PD_MESS_ID(x)		(((x) << 9) & GENMASK(11, 9))
#define SC27XX_PD_POWER_ROLE		BIT(8)
#define SC27XX_PD_SPEC_REV(x)		(((x) << 6) & GENMASK(7, 6))
#define SC27XX_PD_DATA_ROLE		BIT(5)
#define SC27XX_PD_MESSAGE_TYPE(x)	((x) & GENMASK(4, 0))
#define SC27XX_PD_SPEC_MASK		GENMASK(7, 6)

/* Bits definitions for SC27XX_PD_CTRL register */
#define SC27XX_PD_TX_START		BIT(0)
#define SC27XX_PD_HARD_RESET		BIT(2)
#define SC27XX_PD_TX_FLASH		BIT(3)
#define SC27XX_PD_RX_FLASH		BIT(4)
#define SC27XX_PD_FAST_START		BIT(6)
#define SC27XX_PD_CABLE_RESET		BIT(7)
#define SC27XX_PD_RX_ID_CLR		BIT(8)
#define SC27XX_PD_RP_SINKTXNG_CLR	BIT(9)

/* Bits definitions for SC27XX_PD_CFG0 register */
#define SC27XX_PD_RP_CONTROL(x)		((x) & GENMASK(1, 0))
#define SC27XX_PD_SINK_RP		GENMASK(3, 2)
#define SC27XX_PD_EN_SOP1_TX		BIT(6)
#define SC27XX_PD_EN_SOP2_TX		BIT(7)
#define SC27XX_PD_EN_SOP		BIT(8)
#define SC27XX_PD_SRC_SINK_MODE		BIT(9)
#define SC27XX_PD_CTL_EN		BIT(10)
#define SC27XX_PD_BIST_MODE_EN		BIT(11)

/* Bits definitions for SC27XX_PD_CFG1 register */
#define SC27XX_PD_AUTO_RETRY		BIT(0)
#define SC27XX_PD_RETRY(x)		(((x) << 1) & GENMASK(2, 1))
#define SC27XX_PD_HEADER_REG_EN		BIT(3)
#define SC27XX_PD_EN_SOP1_RX		BIT(6)
#define SC27XX_PD_EN_SOP2_RX		BIT(7)
#define SC27XX_PD_EN_SOP_RX		BIT(8)
#define SC27XX_PD_RX_AUTO_GOOD_CRC	BIT(9)
#define SC27XX_PD_FRS_DETECT_EN		BIT(10)
#define SC27XX_PD_PHY_13M		BIT(11)
#define SC27XX_PD_TX_AUTO_GOOD_CRC	BIT(12)

/* Bits definitions for SC27XX_PD_MESG_ID_CFG register */
#define SC27XX_PD_MESS_ID_TX(x)		((x) & GENMASK(2, 0))
#define SC27XX_PD_MESS_ID_RX(x)		(((x) << 4) & GENMASK(6, 4))
#define SC27XX_PD_RETRY_MASK		GENMASK(2, 1)
#define SC27XX_PD_MESS_ID_MASK		GENMASK(2, 0)

/* Bits definitions for SC27XX_TYPEC_SW_CFG register */
#define SC27XX_TYPEC_SW_SWITCH(x)	(((x) << 10) & GENMASK(11, 10))

/* Bits definitions for SC27XX_INT_FLG register */
#define SC27XX_PD_HARD_RST_FLAG		BIT(0)
#define SC27XX_PD_CABLE_RST_FLAG	BIT(1)
#define SC27XX_PD_SOFT_RST_FLAG		BIT(2)
#define SC27XX_PD_PS_RDY_FLAG		BIT(3)
#define SC27XX_PD_PKG_RV_FLAG		BIT(4)
#define SC27XX_PD_TX_OK_FLAG		BIT(5)
#define SC27XX_PD_TX_ERROR_FLAG		BIT(6)
#define SC27XX_PD_TX_COLLSION_FLAG	BIT(7)
#define SC27XX_PD_PKG_RV_ERROR_FLAG	BIT(8)
#define SC27XX_PD_FRS_RV_FLAG		BIT(9)
#define SC27XX_PD_RX_FIFO_OVERFLOW_FLAG	BIT(10)

/* Bits definitions for SC27XX_PD_STS1 register */
#define SC27XX_PD_RX_DATA_NUM_MASK	GENMASK(8, 0)
#define SC27XX_PD_RX_EMPTY		BIT(13)

/* Bits definitions for SC27XX_INT_CLR register */
#define SC27XX_PD_HARD_RST_RV_CLR	BIT(0)
#define SC27XX_PD_CABLE_RST_RV_CLR	BIT(1)
#define SC27XX_PD_SOFT_RST_RV_CLR	BIT(2)
#define SC27XX_PD_PS_RDY_CLR		BIT(3)
#define SC27XX_PD_PKG_RV_CLR		BIT(4)
#define SC27XX_PD_TX_OK_CLR		BIT(5)
#define SC27XX_PD_TX_ERROR_CLR		BIT(6)
#define SC27XX_PD_TX_COLLSION_CLR	BIT(7)
#define SC27XX_PD_PKG_RV_ERROR_CLR	BIT(8)
#define SC27XX_PD_FRS_RV_CLR		BIT(9)
#define SC27XX_PD_RX_FIFO_OVERFLOW_CLR	BIT(10)

/* Bits definitions for SC27XX_INT_EN register */
#define SC27XX_PD_HARD_RST_RV_EN	BIT(0)
#define SC27XX_PD_CABLE_RST_RV_EN	BIT(1)
#define SC27XX_PD_SOFT_RST_RV_EN	BIT(2)
#define SC27XX_PD_PS_RDY_EN		BIT(3)
#define SC27XX_PD_PKG_RV_EN		BIT(4)
#define SC27XX_PD_TX_OK_EN		BIT(5)
#define SC27XX_PD_TX_ERROR_EN		BIT(6)
#define SC27XX_PD_TX_COLLSION_EN	BIT(7)
#define SC27XX_PD_PKG_RV_ERROR_EN	BIT(8)
#define SC27XX_PD_FRS_RV_EN		BIT(9)
#define SC27XX_PD_RX_FIFO_OVERFLOW_EN	BIT(10)

/* SC27XX_PD_PHY_CFG1 */
#define SC27XX_PD_CC1_SW		BIT(3)
#define SC27XX_PD_CC2_SW		BIT(2)

/* SC27XX_PD_PHY_CFG2 */
#define SC27XX_PD_CFG2_PD_CLK_BIT		BIT(6)
#define SC27XX_PD_CFG2_RX_REF_CAL_BIT		BIT(7)
#define SC27XX_PD_CFG2_RX_REF_CAL_SHIFT		7

#define SC27XX_TX_RX_BUF_MASK		GENMASK(15, 0)
#define SC27XX_PD_INT_CLR		GENMASK(13, 0)
#define SC27XX_STATE_MASK		GENMASK(4, 0)
#define SC27XX_EVENT_MASK		GENMASK(15, 0)
#define SC27XX_TYPEC_INT_CLR_MASK	GENMASK(9, 0)
#define SC27XX_PD_HEAD_CONFIG_MASK	GENMASK(15, 0)
#define SC27XX_PD_CFG0_MASK		GENMASK(8, 0)
#define SC27XX_PD_PHY_CFG0_MASK		0x5102
#define	SC27XX_PD_PHY_CFG1_MASK		0x463c
#define SC27XX_PD_PHY_CFG2_MASK		0x40

#define SC27XX_PD_CFG0_RCCAL_MASK	GENMASK(8, 6)
#define SC27XX_PD_CFG0_VTL_MASK		GENMASK(3, 2)
#define SC27XX_PD_CFG0_VTH_MASK		GENMASK(1, 0)
#define SC27XX_PD_CFG0_RCCAL_SHIFT	6
#define SC27XX_PD_CFG0_VTL_SHIFT	2
#define SC27XX_PD_CFG1_VREF_SEL_MASK		GENMASK(7, 6)
#define SC27XX_PD_CFG1_REF_CAL_MASK		GENMASK(14, 12)
#define SC27XX_PD_CFG1_VREF_SEL_SHIFT		6
#define SC27XX_PD_CFG1_REF_CAL_SHIFT		12

#define SC27XX_PD_DATA_MASK		GENMASK(15, 0)
#define SC27XX_INT_CLR_MASK		0x3fff
#define SC27XX_INT_EN_MASK		0x85ff
#define SC27xx_DETECT_TYPEC_DELAY	700

/* chunked extended message */
#define SC27XX_CHUNKED_EXT_MSG_MASK	GENMASK(7, 0)
#define SC27XX_CHUNKED_EXT_MSG_SHIFT	8

/* Timeout (us) for pd data ready according pd datasheet */
#define SC27XX_PD_RDY_TIMEOUT		2000
#define SC27XX_PD_POLL_RAW_STATUS	50

#define SC27XX_TYPEC_VBUS_OK_TIMEOUT	80000
#define SC27XX_TYPEC_VBUS_OK_STATUS	100

/* Timeout (us) for vbus ready according need */
#define SC27XX_PD_VBUS_TIMEOUT		200000
#define SC27XX_PD_POLL_VBUS_STATUS	50

/* pmic compatible */
#define SC2730_RC_EFUSE_SHIFT		9
#define SC2730_REF_EFUSE_SHIFT		12
#define SC2730_DELTA_EFUSE_SHIFT	7

#define UMP9620_RC_EFUSE_SHIFT		5
#define UMP9620_REF_EFUSE_SHIFT		6
#define UMP9620_DELTA_EFUSE_SHIFT	9

#define UMP518_RC_EFUSE_SHIFT		9
#define UMP518_REF_EFUSE_SHIFT		0
#define UMP518_DELTA_EFUSE_SHIFT	9

/* soc compatible */
#define UMS9620_MASK_AON_APB_R2G_ANALOG_BB_TOP_SINDRV_ENA	0x0020
#define UMS9620_REG_AON_APB_MIPI_CSI_POWER_CTRL			0x0350

#define SC27XX_PD_SHIFT(n)		(n)

#define PMIC_SC2730			1
#define PMIC_UMP9620			2
#define PMIC_UMP518			3

#define SC27XX_PD_RX_ERROR_CNT_THRESHOLD	100
#define SC27XX_PD_RX_ERROR_TIME_THRESHOLD	120
#define SC27XX_PD_HARD_RESET_TIME_THRESHOLD	4
#define SC27XX_PD_RX_ERROR_INT_STATUS		0x100

enum sc27xx_state {
	SC27XX_DETACHED_SNK,
	SC27XX_ATTACHWAIT_SNK,
	SC27XX_ATTACHED_SNK,
	SC27XX_DETACHED_SRC,
	SC27XX_ATTACHWAIT_SRC,
	SC27XX_ATTACHED_SRC,
	SC27XX_POWERED_CABLE,
	SC27XX_AUDIO_CABLE,
	SC27XX_DEBUG_CABLE,
};

enum sc27xx_dp_hpd_status {
	SC27XX_DP_HOT_UNPLUG = 0,
	SC27XX_DP_HOT_PLUG,
	SC27XX_DP_HPD_IRQ,
	SC27XX_DP_TYPE_DISCONNECT,
};

enum sc27xx_pd_clk_mode {
	SC27XX_PD_CLK_D6M_A6M = 0,
	SC27XX_PD_CLK_D13M_A6P5M,
	SC27XX_PD_CLK_D13M_A13M,
};

struct sc27xx_pd_variant_data {
	u32 efuse_rc_shift;
	u32 efuse_ref_shift;
	u32 efuse_delta_shift;
	u32 id;
	u32 module_en;
	u32 arm_clk_en0;
	u32 rtc_clk_en0;
	u32 xtl_wait_ctrl0;
	u32 aon_apb_r2g_analog_bb_top_sindrv_ena;
	u32 reg_aon_apb_mipi_csi_power_ctrl;
};


static const struct sc27xx_pd_variant_data ump9620_data = {
	.efuse_rc_shift = UMP9620_RC_EFUSE_SHIFT,
	.efuse_ref_shift = UMP9620_REF_EFUSE_SHIFT,
	.efuse_delta_shift = UMP9620_DELTA_EFUSE_SHIFT,
	.id = PMIC_UMP9620,
	.module_en = UMP9620_MODULE_EN,
	.arm_clk_en0 = UMP9620_ARM_CLK_EN0,
	.rtc_clk_en0 = UMP9620_RTC_CLK_EN0,
	.xtl_wait_ctrl0 = UMP9620_XTL_WAIT_CTRL0,
	.aon_apb_r2g_analog_bb_top_sindrv_ena =
		UMS9620_MASK_AON_APB_R2G_ANALOG_BB_TOP_SINDRV_ENA,
	.reg_aon_apb_mipi_csi_power_ctrl =
		UMS9620_REG_AON_APB_MIPI_CSI_POWER_CTRL,
};


