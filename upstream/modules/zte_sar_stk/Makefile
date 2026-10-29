# ZTE's driver of the U30 Air's Sensortek STK501xx SAR sensor (i2c-2 0x28, "stk,stk501xx"), from ZTE's 5.4 kernel
# (drivers/vendor/common/sensor/sar/stk501xx), ported to the mainline kernels; parity-5.4.txt, FINDINGS 234.
ccflags-y += -DSTK_SPREADTRUM -DSTK_RETRY_I2C -I$(src)
obj-m += zte_sar_stk.o
zte_sar_stk-objs := stk501xx.o stk501xx_qualcomm.o common_i2c.o common_timer.o common_gpio_qualcomm.o common_storage.o
