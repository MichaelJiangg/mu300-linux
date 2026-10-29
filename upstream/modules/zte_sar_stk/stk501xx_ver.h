/**
 *  * @file stk501xx_ver.h
 *  *
 *  * Copyright (c) 2022, Sensortek.
 *  * All rights reserved.
 *  *
 *******************************************************************************/

/*==============================================================================
 *
 *     Change Log:
 *
 *         EDIT HISTORY FOR FILE
 *
 *         MAY 19 2022 STK - 1.0.0
 *         - First draft version
 *         FEB 23 2023 STK - 1.1.0
 *         - Add set dist(threahold using) function.
 *         MAR 03 2023 STK - 1.2.0
 *         - Merge stk501xx_drv_i2c.c to stk501xx_qualcomm.c
 *         - Edit some STK_SPREADTRUM define region
 *         Mar 16 2023 STK - 1.3.0
 *         - Edit symbol int, u16, u32...etc to intxx_t
 *         Mar 21 2023 STK - 1.4.0
 *         - Add TWS using initail setting
 *         Mar 23 2023 STK - 1.5.0
 *         - Modify soft reset flow
 *         - Smothing cadc setting will be check chip index
 *         Apr 21 2023 STK - 1.6.0
 *         - Initial add AFE power timing control
 *         - Add force read STK_ADDR_TRIGGER_CMD
 *         May 10 2023 STK - 1.7.0
 *         - Delta threshold can be set by decimal value,
 *           driver will auto devide gain and sqrt.
 *============================================================================*/

#ifndef _STK501XX_VER_H
#define _STK501XX_VER_H

// 32-bit version number represented as major[31:16].minor[15:8].rev[7:0]
#define STK501XX_MAJOR        1
#define STK501XX_MINOR        7
#define STK501XX_REV          0
#define VERSION_STK501XX  ((STK501XX_MAJOR<<16) | (STK501XX_MINOR<<8) | STK501XX_REV)

#endif //_STK501XX_VER_H
