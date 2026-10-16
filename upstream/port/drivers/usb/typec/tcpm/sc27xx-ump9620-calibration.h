/* SPDX-License-Identifier: GPL-2.0
 * Copyright (C) 2019 Spreadtrum Communications Inc.
 * UMP9620 register definitions and calibration from the ZTE U30 Air GPL tree:
 * https://github.com/Enceka/android_kernel_zte_ums9620_mifi_u30air
 * drivers/usb/typec/tcpm/sc27xx_pd.c. Policy uses mainline TCPM.
 */
static int sc27xx_pd_set_aon_clock(struct sc27xx_pd *pd, bool on)
{
	int ret;
	u32 mask, reg;

	if (!pd->aon_apb) {
		dev_warn(pd->dev, "aon apb NULL\n");
		return 0;
	}

	mask = pd->var_data->aon_apb_r2g_analog_bb_top_sindrv_ena;
	reg = pd->var_data->reg_aon_apb_mipi_csi_power_ctrl;

	if (on) {
		ret = regmap_update_bits(pd->aon_apb, reg, mask, mask);
		if (ret)
			return ret;
	} else {
		ret = regmap_update_bits(pd->aon_apb, reg, mask, ~mask);
		if (ret)
			return ret;
	}

	return 0;
}

static int sc27xx_pd_clk_cfg(struct sc27xx_pd *pd)
{
	int ret;

	ret = regmap_update_bits(pd->regmap, pd->var_data->module_en,
				 SC27XX_TYPEC_PD_EN, SC27XX_TYPEC_PD_EN);
	if (ret)
		return ret;

	ret = regmap_update_bits(pd->regmap, pd->var_data->arm_clk_en0,
				 SC27XX_CLK_PD_EN, SC27XX_CLK_PD_EN);
	if (ret)
		return ret;

	return regmap_update_bits(pd->regmap, pd->var_data->xtl_wait_ctrl0,
				  SC27XX_XTL_EN, SC27XX_XTL_EN);
}

static int sc27xx_pd_disable_clk(struct sc27xx_pd *pd)
{
	int ret;

	ret = regmap_update_bits(pd->regmap, pd->var_data->module_en,
				 SC27XX_TYPEC_PD_EN, 0);
	if (ret)
		return ret;

	return regmap_update_bits(pd->regmap, pd->var_data->arm_clk_en0,
				 SC27XX_CLK_PD_EN, 0);
}

static int sc27xx_pd_rc_ref_cal(struct sc27xx_pd *pd)
{
	u32 vol = 0;
	u32 pd_ref = 0;
	u32 val = 0;
	u32 cfg2_bit7 = 0, cfg0_vth = 0, cfg0_vtl = 0, typec_ibis = 0;
	u32 cfg0, cfg2, cfg0_mask, cfg2_mask = 0;
	int ret;

	vol = (pd->rc_cal >> SC27XX_PD_SHIFT(pd->var_data->efuse_rc_shift)) & 0x7f;
	pd_ref = (pd->ref_cal >> SC27XX_PD_SHIFT(pd->var_data->efuse_ref_shift)) & 0x7;

	/*
	 * According to the datasheet, depending on the calibration
	 * voltage, different register values should be configured.
	 */

	if (vol <= 26)
		val = 0x0;
	if (vol >= 27 && vol <= 37)
		val = 0x1;
	if (vol >= 38 && vol <= 48)
		val = 0x2;
	if (vol >= 49 && vol <= 59)
		val = 0x3;
	if (vol >= 60 && vol <= 69)
		val = 0x4;
	if (vol >= 70 && vol <= 80)
		val = 0x5;
	if (vol >= 81 && vol <= 90)
		val = 0x6;
	if (vol >= 91 && vol <= 127)
		val = 0x7;

	switch (pd_ref) {
	case 0:
		cfg2_bit7 = 0;
		cfg0_vth = 0;
		cfg0_vtl = 2;
		typec_ibis = 0;
		break;
	case 1:
		cfg2_bit7 = 0;
		cfg0_vth = 1;
		cfg0_vtl = 1;
		typec_ibis = 1;
		break;
	case 2:
		cfg2_bit7 = 0;
		cfg0_vth = 1;
		cfg0_vtl = 1;
		typec_ibis = 0;
		break;
	case 3:
		cfg2_bit7 = 1;
		cfg0_vth = 1;
		cfg0_vtl = 1;
		typec_ibis = 0;
		break;
	case 4:
		cfg2_bit7 = 0;
		cfg0_vth = 2;
		cfg0_vtl = 0;
		typec_ibis = 0;
		break;
	}

	if (typec_ibis == 1)
		ret = regmap_update_bits(pd->regmap,
					 pd->typec_base + SC27XX_TYPEC_IBIAS,
					 SC27XX_TYPEC_RX_REF_DECREASE,
					 SC27XX_TYPEC_RX_REF_DECREASE);
	else
		ret = regmap_update_bits(pd->regmap,
					 pd->typec_base + SC27XX_TYPEC_IBIAS,
					 SC27XX_TYPEC_RX_REF_DECREASE, 0);

	cfg0 = (cfg0_vtl << SC27XX_PD_CFG0_VTL_SHIFT) & SC27XX_PD_CFG0_VTL_MASK;
	cfg0 |= (val << SC27XX_PD_CFG0_RCCAL_SHIFT) & SC27XX_PD_CFG0_RCCAL_MASK;
	cfg0 |= cfg0_vth & SC27XX_PD_CFG0_VTH_MASK;
	cfg0_mask = SC27XX_PD_CFG0_RCCAL_MASK |
		    SC27XX_PD_CFG0_VTL_MASK | SC27XX_PD_CFG0_VTH_MASK;

	ret = regmap_update_bits(pd->regmap,
				 pd->base + SC27XX_PD_PHY_CFG0,
				 cfg0_mask, cfg0);
	if (ret < 0)
		return ret;

	cfg2 = (cfg2_bit7 << SC27XX_PD_CFG2_RX_REF_CAL_SHIFT) & 0x80;
	cfg2_mask = SC27XX_PD_CFG2_RX_REF_CAL_BIT;

	return regmap_update_bits(pd->regmap, pd->base + SC27XX_PD_PHY_CFG2,
				  cfg2_mask, cfg2);
}

static int sc27xx_pd_select_clk_mode(struct sc27xx_pd *pd,
				     enum sc27xx_pd_clk_mode pd_clk_mode)
{
	int ret;
	u32 arm_clk_en0_mask, pd_cfg1_mask, pd_phy_cfg2_mask;

	switch (pd_clk_mode) {
	case SC27XX_PD_CLK_D6M_A6M:
		arm_clk_en0_mask = (u32)SC27XX_CLK_PD_SEL;
		pd_cfg1_mask = (u32)~SC27XX_PD_PHY_13M;
		pd_phy_cfg2_mask = (u32)~SC27XX_PD_CFG2_PD_CLK_BIT;
		break;
	case SC27XX_PD_CLK_D13M_A13M:
		arm_clk_en0_mask = (u32)~SC27XX_CLK_PD_SEL;
		pd_cfg1_mask = (u32)SC27XX_PD_PHY_13M;
		pd_phy_cfg2_mask = (u32)~SC27XX_PD_CFG2_PD_CLK_BIT;
		break;
	case SC27XX_PD_CLK_D13M_A6P5M:
	default:
		arm_clk_en0_mask = (u32)~SC27XX_CLK_PD_SEL;
		pd_cfg1_mask = (u32)SC27XX_PD_PHY_13M;
		pd_phy_cfg2_mask = (u32)SC27XX_PD_CFG2_PD_CLK_BIT;
		break;
	}

	ret = regmap_update_bits(pd->regmap, pd->var_data->arm_clk_en0,
				 SC27XX_CLK_PD_SEL, arm_clk_en0_mask);
	if (ret < 0) {
		dev_err(pd->dev, "failed to set arm clk en0, ret = %d\n", ret);
		return ret;
	}

	ret = regmap_update_bits(pd->regmap, pd->base + SC27XX_PD_CFG1,
				 SC27XX_PD_PHY_13M, pd_cfg1_mask);
	if (ret < 0) {
		dev_err(pd->dev, "failed to set pd cfg1 13m, ret = %d\n", ret);
		return ret;
	}

	ret = regmap_update_bits(pd->regmap, pd->base + SC27XX_PD_PHY_CFG2,
				 SC27XX_PD_CFG2_PD_CLK_BIT, pd_phy_cfg2_mask);
	if (ret < 0) {
		dev_err(pd->dev, "failed to set pd cfg2 clk, ret = %d\n", ret);
		return ret;
	}

	return 0;
}

static int sc27xx_pd_delta_cal(struct sc27xx_pd *pd)
{
	u32 delta_cal = pd->delta_cal;
	u32 vol, vref_sel = 0, ref_cal = 0, delta = 0;
	u32 cfg1, cfg1_mask;

	cfg1_mask = SC27XX_PD_CC1_SW | SC27XX_PD_CC2_SW |
		    SC27XX_PD_CFG1_VREF_SEL_MASK |
		    SC27XX_PD_CFG1_REF_CAL_MASK;

	delta = ((delta_cal >> SC27XX_PD_SHIFT(pd->var_data->efuse_delta_shift)) & 0x7f);
	/*
	 * According to the datasheet, delta is efuse caliration
	 * vol = delta * 2 + 1000
	 */
	vol = delta * 2 + 1000;

	/*
	 * According to the datasheet, depending on the calibration
	 * voltage, different register values should be configured.
	 */

	if (vol >= 1185 && vol <= 1195) {
		vref_sel = 0x0;
		ref_cal = 0x0;
	} else if (vol >= 1175 && vol < 1185) {
		vref_sel = 0x0;
		ref_cal = 0x1;
	} else if (vol >= 1165 && vol < 1175) {
		vref_sel = 0x0;
		ref_cal = 0x2;
	} else if (vol >= 1155 && vol < 1165) {
		vref_sel = 0x0;
		ref_cal = 0x3;
	} else if (vol >= 1145 && vol < 1155) {
		vref_sel = 0x0;
		ref_cal = 0x4;
	} else if (vol >= 1135 && vol < 1145) {
		vref_sel = 0x0;
		ref_cal = 0x5;
	} else if (vol >= 1125 && vol < 1135) {
		vref_sel = 0x0;
		ref_cal = 0x6;
	} else if (vol >= 1115 && vol < 1125) {
		vref_sel = 0x1;
		ref_cal = 0x2;
	} else if (vol >= 1105 && vol < 1115) {
		vref_sel = 0x1;
		ref_cal = 0x3;
	} else if (vol >= 1095 && vol < 1105) {
		vref_sel = 0x1;
		ref_cal = 0x4;
	} else if (vol >= 1085 && vol < 1095) {
		vref_sel = 0x1;
		ref_cal = 0x5;
	} else if (vol >= 1075 && vol < 1085) {
		vref_sel = 0x1;
		ref_cal = 0x6;
	} else if (vol >= 1065 && vol < 1075) {
		vref_sel = 0x2;
		ref_cal = 0x2;
	} else if (vol >= 1055 && vol < 1065) {
		vref_sel = 0x2;
		ref_cal = 0x3;
	} else if (vol >= 1045 && vol < 1055) {
		vref_sel = 0x2;
		ref_cal = 0x4;
	} else if (vol >= 1035 && vol < 1045) {
		vref_sel = 0x2;
		ref_cal = 05;
	} else if (vol >= 1025 && vol < 1035) {
		vref_sel = 0x2;
		ref_cal = 0x6;
	} else if (vol >= 1015 && vol < 1025) {
		vref_sel = 0x3;
		ref_cal = 0x2;
	} else if (vol >= 1005 && vol < 1015) {
		vref_sel = 0x3;
		ref_cal = 0x3;
	} else if (vol >= 1000 && vol < 1005) {
		vref_sel = 0x3;
		ref_cal = 0x4;
	}

	cfg1 = SC27XX_PD_CC1_SW | SC27XX_PD_CC2_SW;
	cfg1 |= (vref_sel << SC27XX_PD_CFG1_VREF_SEL_SHIFT)
		& SC27XX_PD_CFG1_VREF_SEL_MASK;
	cfg1 |= (ref_cal << SC27XX_PD_CFG1_REF_CAL_SHIFT)
		& SC27XX_PD_CFG1_REF_CAL_MASK;

	return regmap_update_bits(pd->regmap, pd->base + SC27XX_PD_PHY_CFG1,
				  cfg1_mask, cfg1);
}

static int sc27xx_pd_efuse_read(struct sc27xx_pd *pd,
				const char *cell_id, u32 *val)
{
	struct nvmem_cell *cell;
	void *buf;
	size_t len = 0;

	cell = nvmem_cell_get(pd->dev, cell_id);
	if (IS_ERR_OR_NULL(cell))
		return PTR_ERR(cell);

	buf = nvmem_cell_read(cell, &len);
	nvmem_cell_put(cell);

	if (IS_ERR(buf))
		return PTR_ERR(buf);

	memcpy(val, buf, min(len, sizeof(u16)));

	kfree(buf);
	return 0;
}

static int sc27xx_pd_cal(struct sc27xx_pd *pd)
{
	int ret;

	ret = sc27xx_pd_efuse_read(pd, "pdrc_calib", &pd->rc_cal);
	if (ret)
		return ret;

	ret = sc27xx_pd_efuse_read(pd, "pddelta_calib", &pd->delta_cal);
	if (ret)
		return ret;

	if (pd->var_data->id == PMIC_SC2730 || pd->var_data->id == PMIC_UMP518) {
		ret = sc27xx_pd_efuse_read(pd, "pdref_calib", &pd->ref_cal);
		if (ret)
			return ret;
	} else if (pd->var_data->id == PMIC_UMP9620) {
		/*
		 * ump9620 pdref_calib use the same block
		 * with pddelta_calib--block 36.
		 */
		ret = sc27xx_pd_efuse_read(pd, "pddelta_calib", &pd->ref_cal);
		if (ret)
			return ret;
	}

	return 0;
}
