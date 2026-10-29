#include "stk501xx.h"

#if defined STK_INTERRUPT_MODE
static void stk_work_queue(stk_gpio_info *gpio_info);
#elif defined STK_POLLING_MODE
static void stk_work_queue(stk_timer_info *t_info);
#endif

#ifdef MCU_GESTURE
    static void stk_alg_work_queue(stk_timer_info * t_info);
#endif

stk501xx_register_table stk501xx_default_register_table[] = {
    // Trigger_CMD
    {STK_ADDR_TRIGGER_REG,          STK_TRIGGER_REG_PHEN_DISABLE_ALL},
    {STK_ADDR_TRIGGER_CMD,          STK_TRIGGER_CMD_REG_INIT_ALL    },

    // RXIO 0~7
    {STK_ADDR_RXIO0_MUX_REG,        STK_RXIO0_MUX_REG_VALUE}, //mapping ph1
    {STK_ADDR_RXIO1_MUX_REG,        STK_RXIO1_MUX_REG_VALUE}, //mapping ph2
    {STK_ADDR_RXIO2_MUX_REG,        STK_RXIO2_MUX_REG_VALUE},
    {STK_ADDR_RXIO3_MUX_REG,        STK_RXIO3_MUX_REG_VALUE},
    {STK_ADDR_RXIO4_MUX_REG,        STK_RXIO4_MUX_REG_VALUE},
    {STK_ADDR_RXIO5_MUX_REG,        STK_RXIO5_MUX_REG_VALUE},
    {STK_ADDR_RXIO6_MUX_REG,        STK_RXIO6_MUX_REG_VALUE},
    {STK_ADDR_RXIO7_MUX_REG,        STK_RXIO7_MUX_REG_VALUE},

    // SCAN_PERIOD
    {STK_ADDR_SCAN_PERIOD,         STK_SCAN_PERIOD_VALUE},

    // I2C WDT
    {STK_ADDR_I2C_WDT_CTRL,        STK_I2C_WDT_VALUE},

    // below by function to set each phase
    // SCAN OPTION
    {STK_ADDR_SCAN_OPT_PH0,        STK_SCAN_OPT_PH0_VALUE},
    {STK_ADDR_SCAN_OPT_PH1,        STK_SCAN_OPT_PH1_VALUE},
    {STK_ADDR_SCAN_OPT_PH2,        STK_SCAN_OPT_PH2_VALUE},
    {STK_ADDR_SCAN_OPT_PH3,        STK_SCAN_OPT_PH3_VALUE},
    {STK_ADDR_SCAN_OPT_PH4,        STK_SCAN_OPT_PH4_VALUE},
    {STK_ADDR_SCAN_OPT_PH5,        STK_SCAN_OPT_PH5_VALUE},
    {STK_ADDR_SCAN_OPT_PH6,        STK_SCAN_OPT_PH6_VALUE},
    {STK_ADDR_SCAN_OPT_PH7,        STK_SCAN_OPT_PH7_VALUE},

    // TX CTRL
    {STK_ADDR_TX_CTRL_PH0,         STK_TX_CTRL_PH0_VALUE},
    {STK_ADDR_TX_CTRL_PH1,         STK_TX_CTRL_PH1_VALUE},
    {STK_ADDR_TX_CTRL_PH2,         STK_TX_CTRL_PH2_VALUE},
    {STK_ADDR_TX_CTRL_PH3,         STK_TX_CTRL_PH3_VALUE},
    {STK_ADDR_TX_CTRL_PH4,         STK_TX_CTRL_PH4_VALUE},
    {STK_ADDR_TX_CTRL_PH5,         STK_TX_CTRL_PH5_VALUE},
    {STK_ADDR_TX_CTRL_PH6,         STK_TX_CTRL_PH6_VALUE},
    {STK_ADDR_TX_CTRL_PH7,         STK_TX_CTRL_PH7_VALUE},

    // SENS_CTRL
    {STK_ADDR_SENS_CTRL_PH0,       STK_SENS_CTRL_PH0_VALUE},
    {STK_ADDR_SENS_CTRL_PH1,       STK_SENS_CTRL_PH1_VALUE},
    {STK_ADDR_SENS_CTRL_PH2,       STK_SENS_CTRL_PH2_VALUE},
    {STK_ADDR_SENS_CTRL_PH3,       STK_SENS_CTRL_PH3_VALUE},
    {STK_ADDR_SENS_CTRL_PH4,       STK_SENS_CTRL_PH4_VALUE},
    {STK_ADDR_SENS_CTRL_PH5,       STK_SENS_CTRL_PH5_VALUE},
    {STK_ADDR_SENS_CTRL_PH6,       STK_SENS_CTRL_PH6_VALUE},
    {STK_ADDR_SENS_CTRL_PH7,       STK_SENS_CTRL_PH7_VALUE},

    // FILTER_CFG_SETTING
    {STK_ADDR_FILT_CFG_PH0,       STK_FILT_CFG_PH0_VALUE},
    {STK_ADDR_FILT_CFG_PH1,       STK_FILT_CFG_PH1_VALUE},
    {STK_ADDR_FILT_CFG_PH2,       STK_FILT_CFG_PH2_VALUE},
    {STK_ADDR_FILT_CFG_PH3,       STK_FILT_CFG_PH3_VALUE},
    {STK_ADDR_FILT_CFG_PH4,       STK_FILT_CFG_PH4_VALUE},
    {STK_ADDR_FILT_CFG_PH5,       STK_FILT_CFG_PH5_VALUE},
    {STK_ADDR_FILT_CFG_PH6,       STK_FILT_CFG_PH6_VALUE},
    {STK_ADDR_FILT_CFG_PH7,       STK_FILT_CFG_PH7_VALUE},

    // CORRECTION
    {STK_ADDR_CORRECTION_PH0,     STK_CORRECTION_PH0_VALUE},
    {STK_ADDR_CORRECTION_PH1,     STK_CORRECTION_PH1_VALUE},
    {STK_ADDR_CORRECTION_PH2,     STK_CORRECTION_PH2_VALUE},
    {STK_ADDR_CORRECTION_PH3,     STK_CORRECTION_PH3_VALUE},
    {STK_ADDR_CORRECTION_PH4,     STK_CORRECTION_PH4_VALUE},
    {STK_ADDR_CORRECTION_PH5,     STK_CORRECTION_PH5_VALUE},
    {STK_ADDR_CORRECTION_PH6,     STK_CORRECTION_PH6_VALUE},
    {STK_ADDR_CORRECTION_PH7,     STK_CORRECTION_PH7_VALUE},

    {STK_ADDR_CORR_ENGA_0,        0x0},
    {STK_ADDR_CORR_ENGA_1,        0x0},
    {STK_ADDR_CORR_ENGB_0,        0x0},
    {STK_ADDR_CORR_ENGB_1,        0x0},
    {STK_ADDR_CORR_ENGC_0,        0x0},
    {STK_ADDR_CORR_ENGC_1,        0x0},
    {STK_ADDR_CORR_ENGD_0,        0x0},
    {STK_ADDR_CORR_ENGD_1,        0x0},

    // NOISE DET
    {STK_ADDR_NOISE_DECT_PH0,     STK_NOISE_DECT_PH0_VALUE},
    {STK_ADDR_NOISE_DECT_PH1,     STK_NOISE_DECT_PH1_VALUE},
    {STK_ADDR_NOISE_DECT_PH2,     STK_NOISE_DECT_PH2_VALUE},
    {STK_ADDR_NOISE_DECT_PH3,     STK_NOISE_DECT_PH3_VALUE},
    {STK_ADDR_NOISE_DECT_PH4,     STK_NOISE_DECT_PH4_VALUE},
    {STK_ADDR_NOISE_DECT_PH5,     STK_NOISE_DECT_PH5_VALUE},
    {STK_ADDR_NOISE_DECT_PH6,     STK_NOISE_DECT_PH6_VALUE},
    {STK_ADDR_NOISE_DECT_PH7,     STK_NOISE_DECT_PH7_VALUE},

    // CADC_OPTION
    {STK_ADDR_CADC_OPT0_PH0,     STK_CADC_OPT0_PH0_VALUE},
    {STK_ADDR_CADC_OPT0_PH1,     STK_CADC_OPT0_PH1_VALUE},
    {STK_ADDR_CADC_OPT0_PH2,     STK_CADC_OPT0_PH2_VALUE},
    {STK_ADDR_CADC_OPT0_PH3,     STK_CADC_OPT0_PH3_VALUE},
    {STK_ADDR_CADC_OPT0_PH4,     STK_CADC_OPT0_PH4_VALUE},
    {STK_ADDR_CADC_OPT0_PH5,     STK_CADC_OPT0_PH5_VALUE},
    {STK_ADDR_CADC_OPT0_PH6,     STK_CADC_OPT0_PH6_VALUE},
    {STK_ADDR_CADC_OPT0_PH7,     STK_CADC_OPT0_PH7_VALUE},

    // START UP THERSHOLD
    {STK_ADDR_STARTUP_THD_PH0,   STK_STARTUP_THD_PH0_VALUE},
    {STK_ADDR_STARTUP_THD_PH1,   STK_STARTUP_THD_PH1_VALUE},
    {STK_ADDR_STARTUP_THD_PH2,   STK_STARTUP_THD_PH2_VALUE},
    {STK_ADDR_STARTUP_THD_PH3,   STK_STARTUP_THD_PH3_VALUE},
    {STK_ADDR_STARTUP_THD_PH4,   STK_STARTUP_THD_PH4_VALUE},
    {STK_ADDR_STARTUP_THD_PH5,   STK_STARTUP_THD_PH5_VALUE},
    {STK_ADDR_STARTUP_THD_PH6,   STK_STARTUP_THD_PH6_VALUE},
    {STK_ADDR_STARTUP_THD_PH7,   STK_STARTUP_THD_PH7_VALUE},

    // PROX_CTRL_0
    {STK_ADDR_PROX_CTRL0_PH0,   STK_PROX_CTRL0_PH0_VALUE},
    {STK_ADDR_PROX_CTRL0_PH1,   STK_PROX_CTRL0_PH1_VALUE},
    {STK_ADDR_PROX_CTRL0_PH2,   STK_PROX_CTRL0_PH2_VALUE},
    {STK_ADDR_PROX_CTRL0_PH3,   STK_PROX_CTRL0_PH3_VALUE},
    {STK_ADDR_PROX_CTRL0_PH4,   STK_PROX_CTRL0_PH4_VALUE},
    {STK_ADDR_PROX_CTRL0_PH5,   STK_PROX_CTRL0_PH5_VALUE},
    {STK_ADDR_PROX_CTRL0_PH6,   STK_PROX_CTRL0_PH6_VALUE},
    {STK_ADDR_PROX_CTRL0_PH7,   STK_PROX_CTRL0_PH7_VALUE},

    // PROX_CTRL_1
    {STK_ADDR_PROX_CTRL1_PH0,   STK_PROX_CTRL1_PH0_VALUE},
    {STK_ADDR_PROX_CTRL1_PH1,   STK_PROX_CTRL1_PH1_VALUE},
    {STK_ADDR_PROX_CTRL1_PH2,   STK_PROX_CTRL1_PH2_VALUE},
    {STK_ADDR_PROX_CTRL1_PH3,   STK_PROX_CTRL1_PH3_VALUE},
    {STK_ADDR_PROX_CTRL1_PH4,   STK_PROX_CTRL1_PH4_VALUE},
    {STK_ADDR_PROX_CTRL1_PH5,   STK_PROX_CTRL1_PH5_VALUE},
    {STK_ADDR_PROX_CTRL1_PH6,   STK_PROX_CTRL1_PH6_VALUE},
    {STK_ADDR_PROX_CTRL1_PH7,   STK_PROX_CTRL1_PH7_VALUE},
    // set each phase end

    // ADAPTIVE BASELINE FILTER
    {STK_ADDR_ADP_BASELINE_0,   STK_ADP_BASELINE_0_VALUE},
    {STK_ADDR_ADP_BASELINE_1,   STK_ADP_BASELINE_1_VALUE},
    {STK_ADDR_ADP_BASELINE_2,   STK_ADP_BASELINE_2_VALUE},

    // DELTA DES CTRL
    {STK_ADDR_DELTADES_A_CTRL,   0x0},
    {STK_ADDR_DELTADES_B_CTRL,   0x0},
    {STK_ADDR_DELTADES_C_CTRL,   0x0},

    // CUSTOM_SETTING
    {STK_ADDR_CUSTOM_A_CTRL0,   0x0},
    {STK_ADDR_CUSTOM_A_CTRL1,   0x0},
    {STK_ADDR_CUSTOM_B_CTRL0,   0x0},
    {STK_ADDR_CUSTOM_B_CTRL1,   0x0},
    {STK_ADDR_CUSTOM_C_CTRL0,   0x0},
    {STK_ADDR_CUSTOM_C_CTRL1,   0x0},
    {STK_ADDR_CUSTOM_D_CTRL0,   0x0},
    {STK_ADDR_CUSTOM_D_CTRL1,   0x0},

    // DISABLE SMOTH CADC , unlock OTP
    {STK_ADDR_INHOUSE_CMD,   0xA},
    {STK_ADDR_TRIM_LOCK,     0xA5},
    {STK_ADDR_CADC_SMOOTH,   0x0},
    {0x0740,                 0x0413AA},
    {STK_ADDR_TRIM_LOCK,     0x5A},
    {STK_ADDR_INHOUSE_CMD,   0x5},

    // CADC DEGLITCH
    {STK_ADDR_FAIL_STAT_DET_2, STK_FAIL_STAT_DET_2_VALUE}, //update when CADC change more than 5 times

    // IRQ
    {STK_ADDR_IRQ_SOURCE_ENABLE_REG, (1 << STK_IRQ_SOURCE_ENABLE_REG_CLOSE_ANY_IRQ_EN_SHIFT) |
        (1 << STK_IRQ_SOURCE_ENABLE_REG_FAR_ANY_IRQ_EN_SHIFT) | (1 << STK_IRQ_SOURCE_ENABLE_REG_PHRST_IRQ_EN_SHIFT)
#ifdef TEMP_COMPENSATION
        | (1 <<STK_IRQ_SOURCE_ENABLE_REG_DELTA_DES_IRQ_EN_SHIFT)
#endif
    },
#ifdef TEMP_COMPENSATION
    {STK_ADDR_DELTADES_A_CTRL, STK_ADDR_DELTADES_A_CTRL_VALUE}, //enable delta descend
#endif

#ifndef STK_INTERRUPT_MODE
    // Resolve sensing and i2c bus collision
    {STK_ADDR_IRQ_CONFIG, (1 << STK_IRQ_CONFIG_SENS_RATE_OPT_SHIFT)},
#endif
};

/****************************************************************************************************
* 16bit register address function
****************************************************************************************************/
int32_t stk501xx_read(struct stk_data* stk, unsigned short addr, void *buf)
{
    return STK501XX_REG_READ_BLOCK(stk, addr, 4, buf);
}

int32_t stk501xx_write(struct stk_data* stk, unsigned short addr, unsigned char* val)
{
    return STK501XX_REG_WRITE_BLOCK(stk, addr, val, 4);
}

/****************************************************************************************************
* SAR control API
****************************************************************************************************/
static int32_t stk_register_queue(struct stk_data *stk)
{
#ifdef STK_INTERRUPT_MODE
    uint8_t err = 0;

#ifdef STK_MTK
    // need to request int_pin in sar and use common_gpio_mtk.c
    if (gpio_request(stk->int_pin, "stk_sar_int")) {
        STK_SAR_ERR("gpio_request failed");
        return -1;
    }
#endif

    STK_SAR_ERR("gpio_request int32_t=%d", stk->gpio_info.int_pin);
    strcpy(stk->gpio_info.wq_name, "stk_sar_int");
    strcpy(stk->gpio_info.device_name, "stk_sar_irq");
    stk->gpio_info.gpio_cb = stk_work_queue;
    stk->gpio_info.trig_type = TRIGGER_FALLING;
#ifdef STK_QUALCOMM
    stk->gpio_info.trig_type = TRIGGER_LOW;
#endif
    stk->gpio_info.is_active = false;
    stk->gpio_info.is_exist = false;
    stk->gpio_info.any = stk;

    err = STK_GPIO_IRQ_REGISTER(stk, &stk->gpio_info);
    err |= STK_GPIO_IRQ_START(stk, &stk->gpio_info);
    if (0 > err) {
        return -1;
    }
#endif /* STK_INTERRUPT_MODE */

#if defined STK_POLLING_MODE || defined MCU_GESTURE
    strcpy(stk->stk_timer_info.wq_name, "stk_wq");
    stk->stk_timer_info.timer_unit = U_SECOND;
    stk->stk_timer_info.interval_time = STK_POLLING_TIME;
#ifdef STK_POLLING_MODE
    stk->stk_timer_info.timer_cb = stk_work_queue;
#else /* MCU_GESTURE */
    stk->stk_timer_info.timer_cb = stk_alg_work_queue;
#endif /* STK_POLLING_MODE, MCU_GESTURE */
    stk->stk_timer_info.is_active = false;
    stk->stk_timer_info.is_exist = false;
    stk->stk_timer_info.any = stk;
    STK_TIMER_REGISTER(stk, &stk->stk_timer_info);
#endif /* STK_INTERRUPT_MODE, STK_POLLING_MODE */

    return 0;
}

#ifdef TEMP_COMPENSATION
void temperature_compensation(struct stk_data *stk, uint32_t int_flag, uint16_t prox_flag)
{
    uint16_t reg = 0;
    uint32_t delta_des = 0, val = 0;

    if ((int_flag & STK_IRQ_SOURCE_CLOSE_IRQ_MASK) &&
        (prox_flag & (1<< DELDEA_A_MAPPING_PHASE))) {
        stk501xx_read_temp_data(stk, &stk->temperature_1);
    } else if(int_flag & STK_IRQ_SOURCE_ENABLE_REG_DELTA_DES_IRQ_EN_MASK) {
        STK_REG_READ(stk, STK_ADDR_DETECT_STATUS_4, (uint8_t*)&delta_des);
        if(delta_des & STK_DETECT_STATUS_4_DES_STAT_A_MASK) {
            stk501xx_read_temp_data(stk, &stk->temperature_2);

            if( (STK_ABS(stk->temperature_1) - STK_ABS(stk->temperature_2)) > DELTA_TEMP_THD) {
                reg = STK_ADDR_TRIGGER_REG;
                val = STK_TRIGGER_REG_PHRST_PHASE;
                STK_REG_WRITE(stk, reg, (uint8_t*)&val);
                reg = STK_ADDR_TRIGGER_CMD;
                val = STK_TRIGGER_CMD_REG_BY_PHRST;
                STK_REG_WRITE(stk, reg, (uint8_t*)&val);
                //force read again
                STK_REG_READ(stk, STK_ADDR_TRIGGER_CMD, (uint8_t*)&val);
            }
        }
    }
}

static void clr_temp(struct stk_data* stk)
{
    stk->temperature_1 = 0;
    stk->temperature_2 = 0;
}
#endif

static uint16_t stk_sqrt(uint32_t delta_value)
{
    uint32_t temp, sqrt;

    sqrt = delta_value / 2;
    temp = 0;

    while (sqrt != temp) {
        temp = sqrt;
        sqrt = ( delta_value/temp + temp) / 2;
    }

    return (uint16_t)sqrt;
}

static int32_t stk501xx_set_thd(struct stk_data* stk)
{
    uint8_t  i =0;
    uint16_t reg, denominator = 0;
    uint32_t val = 0;

    STK_SAR_LOG("stk_ps_set_thd");

    // set threshold gain
    for (i = 0; i < 8; i++) {
        reg = STK_ADDR_PROX_CTRL1_PH0 + (i*0x40);
        STK_REG_READ(stk, reg, (uint8_t*)&val);
        val |= DIST_GAIN_4;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
    }

    STK_REG_READ(stk, STK_ADDR_PROX_CTRL1_PH0, (uint8_t*)&val);
    val &=0x07;
    switch(val) {
        case DIST_GAIN_512:
            denominator = 512;
            break;
        case DIST_GAIN_256:
            denominator = 256;
            break;
        case DIST_GAIN_128:
            denominator = 128;
            break;
        case DIST_GAIN_64:
            denominator = 64;
            break;
        case DIST_GAIN_32:
            denominator = 32;
            break;
        case DIST_GAIN_16:
            denominator = 16;
            break;
        case DIST_GAIN_8:
            denominator = 8;
            break;
        case DIST_GAIN_4:
            denominator = 4;
            break;
    }

    //PH0 threshold
    reg = STK_ADDR_PROX_CTRL0_PH0;
    val = stk_sqrt(STK_SAR_THD_0 / denominator);
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //PH1 threshold
    reg = STK_ADDR_PROX_CTRL0_PH1;
    val = stk_sqrt(STK_SAR_THD_1 / denominator);
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //PH2 threshold
    reg = STK_ADDR_PROX_CTRL0_PH2;
    val = stk_sqrt(STK_SAR_THD_2 / denominator);
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //PH3 threshold
    reg = STK_ADDR_PROX_CTRL0_PH3;
    val = stk_sqrt(STK_SAR_THD_3 / denominator);
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //PH4 threshold
    reg = STK_ADDR_PROX_CTRL0_PH4;
    val = stk_sqrt(STK_SAR_THD_4 / denominator);
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //PH5 threshold
    reg = STK_ADDR_PROX_CTRL0_PH5;
    val = stk_sqrt(STK_SAR_THD_5 / denominator);
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    return 0;
}

static void stk_clr_intr(struct stk_data* stk, uint32_t* flag)
{
    if (0 > STK_REG_READ(stk, STK_ADDR_IRQ_SOURCE, (uint8_t*)flag)) {
        STK_SAR_ERR("read STK_ADDR_IRQ_SOURCE fail");
        return;
    }

    STK_SAR_ERR("stk_clr_intr:: state = 0x%x", *flag);
}

int32_t stk_read_prox_flag(struct stk_data* stk, uint32_t* prox_flag)
{
    int32_t ret = 0;

    ret = STK_REG_READ(stk, STK_ADDR_DETECT_STATUS_1, (uint8_t*)prox_flag);
    if (0 > ret) {
        STK_SAR_ERR("read STK_ADDR_DETECT_STATUS_1 fail");
        return ret;
    }

    STK_SAR_ERR("stk_read_prox_flag:: state = 0x%x", *prox_flag);
    *prox_flag &= STK_DETECT_STATUS_1_PROX_STATE_MASK;

    return ret;
}

void stk501xx_set_enable(struct stk_data* stk, char enable)
{
    uint16_t i, reg = 0;
    uint32_t val = 0, flag = 0;
    STK_SAR_ERR("stk501xx_set_enable en=%d", enable);

    if (enable) {
        stk501xx_set_thd(stk);
#if 0 //pause mode
        reg = STK_ADDR_TRIGGER_CMD;
        val = STK_TRIGGER_REG_EXIT_PAUSE_MODE;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
#else
        reg = STK_ADDR_TRIGGER_REG;
        val = STK_TRIGGER_REG_INIT_ALL;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
        reg = STK_ADDR_TRIGGER_CMD;
        val = STK_TRIGGER_CMD_REG_INIT_ALL;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
        //force read again
        STK_REG_READ(stk, STK_ADDR_TRIGGER_CMD, (uint8_t*)&val);
#endif
#ifdef STK_INTERRUPT_MODE
        /* do nothing */
#elif defined STK_POLLING_MODE
        STK_TIMER_START(stk, &stk->stk_timer_info);
#endif /* STK_INTERRUPT_MODE, STK_POLLING_MODE */
    } else {
#ifdef STK_INTERRUPT_MODE
        /* do nothing */
#elif defined STK_POLLING_MODE
        STK_TIMER_STOP(stk, &stk->stk_timer_info);
#endif /* STK_INTERRUPT_MODE, STK_POLLING_MODE */

        for (i = 0; i < (sizeof(stk->state_change)/ sizeof(uint8_t)); i++) {
            stk->last_nearby[i] = STK_SAR_NEAR_BY_UNKNOWN;
            stk->state_change[i] = 0;
        }

#if 0 //pause mode
        reg = STK_ADDR_TRIGGER_CMD;
        val = STK_TRIGGER_REG_ENTER_PAUSE_MODE;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
#else
        //disable phase
        reg = STK_ADDR_TRIGGER_REG;
        val = STK_TRIGGER_REG_PHEN_DISABLE_ALL;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
        reg = STK_ADDR_TRIGGER_CMD;
        val = STK_TRIGGER_CMD_REG_INIT_ALL;
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
        //force read again
        STK_REG_READ(stk, STK_ADDR_TRIGGER_CMD, (uint8_t*)&val);
#endif
#ifdef TEMP_COMPENSATION
        clr_temp(stk);
#endif
    }

    stk->enabled = enable;
    stk_clr_intr(stk, &flag);
    STK_SAR_ERR("stk501xx_set_enable DONE");
}

void stk501xx_phase_reset(struct stk_data* stk)
{
    uint16_t reg = 0;
    uint32_t val = 0;

    reg = STK_ADDR_TRIGGER_CMD;
    val = STK_TRIGGER_CMD_REG_BY_PHRST;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //force read again
    STK_REG_READ(stk, STK_ADDR_TRIGGER_CMD, (uint8_t*)&val);
}

void stk501xx_read_temp_data(struct stk_data* stk, int32_t *temperature)
{
    uint16_t reg;
    uint32_t val = 0;
    int32_t output_data = 0;
    int32_t err = 0;

    // Phase 0 is defined to reference
    reg = STK_ADDR_REG_RAW_PH0_REG;
    err = STK_REG_READ(stk, reg, (uint8_t*)&val);
    if (err < 0) {
        STK_SAR_ERR("read STK_ADDR_REG_RAW_PH1_REG fail");
        return;
    }

    if (val & 0x80000000) {
        //2's complement = 1's complement +1
        output_data = ((~val + 1) & 0xFFFFFF80);
        output_data *= -1;
    } else {
        output_data = (int32_t)((val & 0xFFFFFF80));
    }

    *temperature = output_data;
    STK_SAR_ERR("stk501xx_read_temp_data:: temp = %d(0x%X)", output_data, val);
}

void stk501xx_read_sar_data(struct stk_data* stk ,uint32_t prox_flag)
{
    uint16_t reg;
    uint32_t raw_val[8], delta_val[8], cadc_val[8];
    int32_t raw_conv_data[8] = { 0 };
    int32_t delta_conv_data[8] = { 0 };
    int32_t i = 0;
    int32_t err = 0;
    uint8_t  be_reset = 0;

    STK_SAR_LOG("stk501xx_read_sar_data start");

#ifdef MCU_GESTURE
#ifdef STK_INTERRUPT_MODE
    // near start timer
    if (((prox_flag >> 8) & GESTURE_PHASE_CHECK) != 0) {
        if (!stk->gs_timer_is_running) {
            // start timer
            STK_TIMER_START(stk, &stk->stk_timer_info);
        }
        stk->gs_timer_is_running = true;
        stk->gs_idle_count = 0;
    }
#endif
    stk->gesture_state = STK_identifyGesture(prox_flag >> 8, false);
#endif
    for (i = 0; i < (sizeof(stk->state_change)/ sizeof(uint8_t)); i++) {
        if (((stk->phase_use_flag >> i) & 0x01) == 0) {
            // STK_SAR_ERR("stk_report_sar_data:: phase %d not used", i);
            continue;
        }

        //read raw data
        reg = STK_ADDR_REG_RAW_PH0_REG + (i * 0x04);
        err = STK_REG_READ(stk, reg, (uint8_t*)&raw_val[i]);
        if (err < 0) {
            STK_SAR_ERR("read STK_ADDR_REG_RAW_PH0_REG fail");
            return;
        }

        if (raw_val[i] & 0x80000000) {
            //2's complement = 1's complement +1
            raw_conv_data[i] = ((~raw_val[i] + 1) & 0xFFFFFF80);
            raw_conv_data[i] *= -1;
        } else {
            raw_conv_data[i] = (int32_t)((raw_val[i] & 0xFFFFFF80));
        }

        STK_SAR_ERR("stk501xx_read_sar_data:: raw[%d] = %d", i, raw_conv_data[i]);

        //read delta data
        reg = STK_ADDR_REG_DELTA_PH0_REG + (i * 0x04);
        err = STK_REG_READ(stk, reg, (uint8_t*)&delta_val[i]);
        if (err < 0) {
            STK_SAR_ERR("read STK_ADDR_REG_DELTA_PH0_REG fail");
            return;
        }

        if (delta_val[i] & 0x80000000) {
            //2's complement = 1's complement +1
            delta_conv_data[i] = ((~delta_val[i] + 1) & 0xFFFFFF80);
            delta_conv_data[i] *= -1;
        } else {
            delta_conv_data[i] = (int32_t)((delta_val[i] & 0xFFFFFF80));
        }

        stk->last_data[i] = delta_conv_data[i];
        STK_SAR_ERR("stk501xx_read_sar_data:: delta[%d] = %d", i, delta_conv_data[i]);

        //read CADC data
        reg = STK_ADDR_REG_CADC_PH0_REG + (i * 0x04);
        err = STK_REG_READ(stk, reg, (uint8_t*)&cadc_val[i]);
        if (err < 0) {
            STK_SAR_ERR("read STK_ADDR_REG_CADC_PH0_REG fail");
            return;
        }

        STK_SAR_ERR("stk501xx_read_sar_data:: CADC[%d] = %d", i, cadc_val[i]);

        // prox_flag state
        if (prox_flag & ((1 << i) << 8) ) { //near
            if (STK_SAR_NEAR_BY != stk->last_nearby[i]) {
                stk->state_change[i] = 1;
                stk->last_nearby[i] = STK_SAR_NEAR_BY;
            } else {
                stk->state_change[i] = 0;
            }
        } else { //far
            if (STK_SAR_FAR_AWAY != stk->last_nearby[i]) {
                stk->state_change[i] = 1;
                stk->last_nearby[i] = STK_SAR_FAR_AWAY;
            } else {
                stk->state_change[i] = 0;
            }
        }

        if ((STK_CADC_DIFF < (abs(stk->last_cadc[i] - cadc_val[i]))) && 
            (stk->last_cadc[i] > 0)) {
            STK_SAR_ERR("stk_read_sar_data::  Ph[%d] cadc diff bigger than thd = %d",
                        i, STK_CADC_DIFF);
            be_reset = 1;
        }
        stk->last_cadc[i] = cadc_val[i];
    }

    if (be_reset == 1) {
        stk501xx_phase_reset(stk);
    }
}

/*
 * @brief: Initialize some data in stk_data.
 *
 * @param[in/out] stk: struct stk_data *
 */
void stk501xx_data_initialize(struct stk_data* stk)
{
    int32_t i = 0;

    stk->enabled = 0;
    memset(stk->last_data, 0, sizeof(stk->last_data));

    for (i = 0; i < (sizeof(stk->state_change)/ sizeof(uint8_t)); i++) {
        stk->last_nearby[i] = STK_SAR_NEAR_BY_UNKNOWN;
        stk->state_change[i] = 0;
    }

    STK_SAR_LOG("sar initial done");
}

/*
 * @brief: Read PID and write to stk_data.pid.
 *
 * @param[in/out] stk: struct stk_data *
 *
 * @return: Success or fail.
 *          0: Success
 *          others: Fail
 */
static int32_t stk_get_pid(struct stk_data* stk)
{
    int32_t err = 0;
    uint32_t val = 0;
    extern uint8_t is_sar1_exist;

    err = STK_REG_READ(stk, STK_ADDR_CHIP_INDEX, (uint8_t*)&val);
    if (err < 0) {
        STK_SAR_ERR("read STK_ADDR_CHIP_INDEX fail");
        return -1;
    }

    if ((val >> STK_CHIP_INDEX_CHIP_ID__SHIFT) != STK501XX_ID)
        return -1;

    is_sar1_exist = 1;

    stk->chip_id = (val & STK_CHIP_INDEX_CHIP_ID__MASK) >> STK_CHIP_INDEX_CHIP_ID__SHIFT;
    stk->chip_index = val & STK_CHIP_INDEX_F__MASK;
    return err;
}

/*
 * @brief: Read all register (0x0 ~ 0x3F)
 *
 * @param[in/out] stk: struct stk_data *
 * @param[out] show_buffer: record all register value
 *
 * @return: buffer length or fail
 *          positive value: return buffer length
 *          -1: Fail
 */
int32_t stk501xx_show_all_reg(struct stk_data* stk)
{
    int32_t reg_num, reg_count = 0;
    int32_t err = 0;
    uint32_t val = 0;
    uint16_t reg_array[] = {
        STK_ADDR_CHIP_INDEX,
        STK_ADDR_IRQ_SOURCE,
        STK_ADDR_IRQ_SOURCE_ENABLE_REG,
        STK_ADDR_TRIGGER_REG,
        STK_ADDR_TRIGGER_CMD,
        STK_ADDR_RXIO0_MUX_REG,
        STK_ADDR_RXIO1_MUX_REG,
        STK_ADDR_RXIO2_MUX_REG,
        STK_ADDR_RXIO3_MUX_REG,
        STK_ADDR_RXIO4_MUX_REG,
        STK_ADDR_RXIO5_MUX_REG,
        STK_ADDR_RXIO6_MUX_REG,
        STK_ADDR_RXIO7_MUX_REG,
        STK_ADDR_PROX_CTRL0_PH0,
        STK_ADDR_PROX_CTRL0_PH1,
        STK_ADDR_PROX_CTRL0_PH2,
        STK_ADDR_PROX_CTRL0_PH3,
        STK_ADDR_PROX_CTRL0_PH4,
        STK_ADDR_PROX_CTRL0_PH5,
        STK_ADDR_PROX_CTRL0_PH6,
        STK_ADDR_PROX_CTRL0_PH7,
        STK_ADDR_DELTADES_A_CTRL,
    };

    reg_num = sizeof(reg_array) / sizeof(uint16_t);
    STK_SAR_ERR("stk501xx_show_all_reg::");

    for (reg_count = 0; reg_count < reg_num; reg_count++) {
        err = STK_REG_READ(stk, reg_array[reg_count], (uint8_t*)&val);
        if (err < 0) {
            return -1;
        }
        STK_SAR_ERR("reg_array[0x%04x] = 0x%x", reg_array[reg_count], val);
    }

    return 0;
}

static int32_t stk_reg_init(struct stk_data* stk)
{
    int32_t err = 0;
    uint16_t reg, reg_count = 0, reg_num = 0;
    uint32_t val;

    reg_num = sizeof(stk501xx_default_register_table) / sizeof(stk501xx_register_table);

    for (reg_count = 0; reg_count < reg_num; reg_count++) {
        reg = stk501xx_default_register_table[reg_count].address;
        val = stk501xx_default_register_table[reg_count].value;
        if (reg == STK_ADDR_CADC_SMOOTH && stk->chip_index >= 0x1)
            val = 0xFF;

        err = STK_REG_WRITE(stk, reg, (uint8_t*)&val);
        if (err < 0)
            return err;
    }

    //enable phase
    reg = STK_ADDR_TRIGGER_REG;
    val = STK_TRIGGER_REG_INIT_ALL;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    reg = STK_ADDR_TRIGGER_CMD;
    val = STK_TRIGGER_CMD_REG_INIT_ALL;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    //force read again
    STK_REG_READ(stk, STK_ADDR_TRIGGER_CMD, (uint8_t*)&val);

    // set power down for default
    stk501xx_set_enable(stk, 0);
    return 0;
}

/*
 * @brief: SW reset for stk501xx
 *
 * @param[in/out] stk: struct stk_data *
 *
 * @return: Success or fail.
 *          0: Success
 *          others: Fail
 */
int32_t stk501xx_sw_reset(struct stk_data* stk)
{
    int32_t err = 0, i = 0;
    uint16_t reg = STK_ADDR_TRIGGER_REG;
    uint32_t val = STK_TRIGGER_REG_PHEN_DISABLE_ALL;

    err = STK_REG_WRITE(stk, reg, (uint8_t*)&val);
    if (err < 0)
        return err;

    reg = STK_ADDR_TRIGGER_CMD;
    val = STK_TRIGGER_CMD_REG_INIT_ALL;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    reg = STK_ADDR_CHIP_INDEX;
    for(i = 0; i < 2; i++) {
        STK_REG_READ(stk, reg, (uint8_t*)&val);
    }

    reg = STK_ADDR_INHOUSE_CMD;
    val = 0xA;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    reg = 0x1000;
    val = 0xA;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    reg = STK_ADDR_TRIGGER_REG;
    val = 0xFF;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    reg = STK_ADDR_TRIGGER_CMD;
    val = 0xF;
    STK_REG_WRITE(stk, reg, (uint8_t*)&val);

    reg = 0x1004;
    for(i = 0; i < 9; i++) {
        STK_REG_READ(stk, reg, (uint8_t*)&val);
        if( val & 0x10)
            break;
    }

    reg = 0x100C;
    val = 0x00;
    for (i = 0; i < 8; i++) {
        STK_REG_WRITE(stk, reg, (uint8_t*)&val);
        stk->last_nearby[i] = STK_SAR_NEAR_BY_UNKNOWN;
        stk->state_change[i] = 0;
        stk->last_cadc[i] = 0;
    }

    reg = STK_ADDR_SOFT_RESET;
    val = STK_SOFT_RESET_CMD;
    err = STK_REG_WRITE(stk, reg, (uint8_t*)&val);
    if (err < 0)
        return err;

    STK_TIMER_BUSY_WAIT(stk, 1000, 2000, US_RANGE_DELAY);
    return 0;
}

#ifdef MCU_GESTURE
static void stk_alg_work_queue(stk_timer_info * t_info)
{
    uint32_t prox_flag = 0;
    struct stk_data *stk = (struct stk_data*)t_info->any;
    uint16_t err;
    //uint32_t soc_ts = 0;

    //soc_ts = HAL_GetTick();
    //STK_SAR_ERR("stk_alg_work_queue:: Processing, soc_ts=%d\n",soc_ts);

    //read prox flag
    err = stk_read_prox_flag(stk , &prox_flag);
    if (err) {
#ifdef STK_INTERRUPT_MODE
      // after far 600ms stop timer
      if (stk->gs_timer_is_running && !((prox_flag >> 8) & GESTURE_PHASE_CHECK)) {
          if (++stk->gs_idle_count > 6) {
              // stop timer
              STK_TIMER_STOP(stk, &stk->stk_timer_info);
              stk->gs_timer_is_running = false;
          }
      }
#endif
      stk->gesture_state = STK_identifyGesture(prox_flag >> 8, false);
    }
}
#endif /* MCU_GESTURE */

#if defined STK_INTERRUPT_MODE || defined STK_POLLING_MODE
#ifdef STK_INTERRUPT_MODE
static void stk_work_queue(stk_gpio_info *gpio_info)
{
    struct stk_data *stk = (struct stk_data*)gpio_info->any;
#elif defined STK_POLLING_MODE
static void stk_work_queue(stk_timer_info * t_info) {
    struct stk_data *stk = (struct stk_data*)t_info->any;
    uint8_t  err = 0;
    uint16_t reg = 0;
#endif

    uint32_t flag = 0, prox_flag = 0;

#ifdef STK_INTERRUPT_MODE
    STK_SAR_ERR("stk_work_queue:: Interrupt mode");
#elif defined STK_POLLING_MODE
    STK_SAR_ERR("stk_work_queue:: Polling mode");
#endif

    stk_clr_intr(stk, &flag);

    //read prox flag
    stk_read_prox_flag(stk, &prox_flag);

    if (flag & STK_IRQ_SOURCE_SENSING_WDT_IRQ_MASK) {
        STK_SAR_ERR("sensing wdt trigger\n");
        stk501xx_sw_reset(stk);
        stk_reg_init(stk);
        stk501xx_set_enable(stk, true);
    }

#ifdef TEMP_COMPENSATION
    temperature_compensation(stk, flag, prox_flag >> 8);
#endif

    stk501xx_read_sar_data(stk ,prox_flag);

    if (flag & STK_IRQ_SOURCE_FAR_IRQ_MASK ||
            flag & STK_IRQ_SOURCE_CLOSE_IRQ_MASK) {
        STK501XX_SAR_REPORT(stk);
    }

#ifndef STK_INTERRUPT_MODE
    //Resolve sensing and i2c bus collision
    reg = STK_ADDR_SCAN_PERIOD;
    flag = 0;
    err = STK_REG_WRITE(stk, reg , (uint8_t*)&flag);
    if (err < 0) {
        STK_SAR_ERR("write STK_ADDR_SCAN_PERIOD fail");
        return;
    }
#endif
}
#endif /* defined STK_INTERRUPT_MODE || defined STK_POLLING_MODE */

int32_t stk501xx_init_client(struct stk_data * stk)
{
    int32_t err = 0;
    uint32_t flag;

    STK_SAR_LOG("Start Initial stk501xx");

    /* SW reset */
    err = stk501xx_sw_reset(stk);
    if (err < 0) {
        STK_SAR_ERR("software reset error, err=%d", err);
        return err;
    }

    stk_clr_intr(stk, &flag);
    stk501xx_data_initialize(stk);

    err = stk_get_pid(stk);
    if (err < 0) {
        STK_SAR_ERR("stk_get_pid error, err=%d", err);
        return err;
    }
    STK_SAR_LOG("PID 0x%x index=0x%x", stk->chip_id, stk->chip_index);

    err = stk_reg_init(stk);
    if (err < 0) {
        STK_SAR_ERR("stk501xx reg initialization failed");
        return err;
    }

#ifdef MCU_GESTURE
    STK_tws_init();
#endif

    stk_register_queue(stk);

    err = stk501xx_show_all_reg(stk);
    if (err < 0) {
        STK_SAR_ERR("stk501xx_show_all_reg error, err=%d", err);
        return err;
    }

    return 0;
}
