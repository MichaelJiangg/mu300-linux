#include <linux/module.h>
#include <linux/init.h>
#include <linux/slab.h>
#include <linux/i2c.h>
#include <linux/mutex.h>
#include <linux/kdev_t.h>
#include <linux/fs.h>
#include <linux/input.h>
#include <linux/workqueue.h>
#include <linux/irq.h>
#include <linux/delay.h>
#include <linux/sched.h>
#include <linux/kthread.h>
#include <linux/errno.h>
#include <linux/of.h>
#include <linux/types.h>
#include <linux/pm.h>
#include <linux/pm_wakeup.h>
#include <linux/interrupt.h>
#include <linux/gpio.h>
#include <asm/uaccess.h>

#ifndef STK_SPREADTRUM
#ifdef STK_SENSORS_DEV
#include <linux/sensors.h>
#endif
#endif // STK_SPREADTRUM

#include <linux/gpio/consumer.h>

#include "stk501xx.h"
#include "stk501xx_qualcomm.h"

struct attribute_group stk_attribute_sar_group;

/* add zte boardtest interface start */
uint8_t is_sar1_exist = 0;
#ifdef CONFIG_VENDOR_ZTE_MISC_COMMON
#include <vendor/common/zte_misc.h>

int is_sar1_exist_get(char *val, const void *arg)
{
    return snprintf(val, PAGE_SIZE, "%d", is_sar1_exist);
}

static struct zte_misc_ops is_sar1_exist_node = {
    .node_name = "is_sar1_exist",
    .set = NULL,
    .get = is_sar1_exist_get,
    .free = NULL,
    .arg = NULL,
};
#endif
/* zte boardtest interface end */

struct stk501xx_wrapper *stk501xx_wrapper_ptr;
/* MU300: the class files reach the device through stk501xx_wrapper_ptr: set and cleared under this lock */
static DEFINE_MUTEX(stk_class_lock);
static char chip_info[20];

/**
 * @brief: Get power status
 *          Send 0 or 1 to userspace.
 *
 * @param[in] dev: struct device *
 * @param[in] attr: struct device_attribute *
 * @param[in/out] buf: char *
 *
 * @return: ssize_t
 */
static ssize_t stk_enable_show(struct device *dev,
                               struct device_attribute *attr, char *buf)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;
    char en;

    en = stk->enabled;
    return scnprintf(buf, PAGE_SIZE, "enable = %d\n", en);
}

/**
 * @brief: Set power status
 *          Get 0 or 1 from userspace, then set stk8xxx power status.
 *
 * @param[in] dev: struct device *
 * @param[in] attr: struct device_attribute *
 * @param[in/out] buf: char *
 * @param[in] count: size_t
 *
 * @return: ssize_t
 */
static ssize_t stk_enable_store(struct device *dev,
                                struct device_attribute *attr, const char *buf, size_t count)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;
    unsigned int data;
    int error;

    error = kstrtouint(buf, 10, &data);
    if (error) {
        STK_SAR_ERR("kstrtoul failed, error=%d", error);
        return error;
    }

    STK_SAR_ERR("stk_enable_store, data=%d", data);

    if (data > 1)
        return -EINVAL;
    stk501xx_set_enable(stk, data);
    return count;
}

/**
 * @brief: Get sar data
 *          Send sar data to userspce.
 *
 * @param[in] dev: struct device *
 * @param[in] attr: struct device_attribute *
 * @param[in/out] buf: char *
 *
 * @return: ssize_t
 */
static ssize_t stk_value_show(struct device *dev,
                              struct device_attribute *attr, char *buf)
{
    int i = 0;
    uint32_t prox_flag = 0;
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;

    STK_SAR_ERR("stk_value_show");

    //read prox flag
    stk_read_prox_flag(stk, &prox_flag);
    stk501xx_read_sar_data(stk, prox_flag);

    for (i = 0; i < 6; i++) {
        scnprintf(buf, PAGE_SIZE, "ph[%d] value=%d\n", i, stk->last_data[i]);
        STK_SAR_ERR("ph[%d] value=%d\n", i, stk->last_data[i]);
    }

    return 0;
}

static ssize_t stk_flag_show(struct device *dev,
                             struct device_attribute *attr, char *buf)
{
    uint32_t prox_flag = 0;
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;

    STK_SAR_ERR("stk_flag_show");

    //read prox flag
    stk_read_prox_flag(stk, &prox_flag);

    if (prox_flag | 0x0000 ){
        return scnprintf(buf, PAGE_SIZE, "flag is near =%d\n", 1);
    } else {
        return scnprintf(buf, PAGE_SIZE, "flag is far =%d\n", 0);
    }
}

/**
 * @brief: Register writting
 *          Get address and content from userspace, then write to register.
 *
 * @param[in] dev: struct device *
 * @param[in] attr: struct device_attribute *
 * @param[in/out] buf: char *
 * @param[in] count: size_t
 *
 * @return: ssize_t
 */
static ssize_t __maybe_unused stk_send_store(struct device *dev,
                              struct device_attribute *attr, const char *buf, size_t count)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;
    char *token[10];
    int err, i;
    u32 addr, cmd;
    bool enable = false;

    for (i = 0; i < 2; i++)
        token[i] = strsep((char **)&buf, " ");

    err = kstrtouint(token[0], 16, &addr);
    if (err) {
        STK_SAR_ERR("kstrtoint failed, err=%d", err);
        return err;
    }

    err = kstrtoint(token[1], 32, &cmd);
    if (err) {
        STK_SAR_ERR("kstrtoint failed, err=%d", err);
        return err;
    }

    STK_SAR_ERR("write reg[0x%X]=0x%X", addr, cmd);

    if (!stk->enabled)
        stk501xx_set_enable(stk, 1);
    else
        enable = true;

#ifdef STK_FIX_I2C
    unsigned short w_addr = 0x0038;
    unsigned char w_val[4] = { 0xAA, 0x55, 0xAA, 0x55 };
    STK501XX_REG_WRITE_BLOCK(stk, w_addr, w_val, 4);
#endif // STK_FIX_I2C

    if (STK501XX_REG_WRITE_BLOCK(stk, (u16)addr, (u8*)&cmd, 4)) {
        err = -1;
        goto exit;
    }

exit:
    if (!enable)
        stk501xx_set_enable(stk, 0);

    if (err)
        return -1;

    return count;
}

static ssize_t stk_temp_show(struct device *dev,
                             struct device_attribute *attr, char *buf)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;

    STK_SAR_ERR("stk_temp_show");
    stk501xx_read_temp_data(stk, &stk->temperature_1);

    return scnprintf(buf, PAGE_SIZE, "temperature=%d\n", stk->temperature_1);
}

/**
 * @brief: Read all register value, then send result to userspace.
 *
 * @param[in] dev: struct device *
 * @param[in] attr: struct device_attribute *
 * @param[in/out] buf: char *
 *
 * @return: ssize_t
 */
static ssize_t stk_allreg_show(struct device *dev,
                               struct device_attribute *attr, char *buf)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;
    int result;

    result = stk501xx_show_all_reg(stk);
    if (0 > result)
        return result;

    return (ssize_t)result;
}

/**
 * @brief: Check PID, then send chip number to userspace.
 *
 * @param[in] dev: struct device *
 * @param[in] attr: struct device_attribute *
 * @param[in/out] buf: char *
 *
 * @return: ssize_t
 */
static ssize_t stk_chipinfo_show(struct device *dev,
                                 struct device_attribute *attr, char *buf)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    stk_data *stk = &stk_wrapper->stk;

    STK_SAR_ERR("chip id=0x%x, index=0x%x", stk->chip_id, stk->chip_index);
    return scnprintf(buf, PAGE_SIZE, "pid=0x%x,index=0x%x\n", stk->chip_id, stk->chip_index);
}

static ssize_t stk_phase_cali(struct device *dev,
                              struct device_attribute *attr, char *buf)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    int result = 0;
    stk_data *stk = &stk_wrapper->stk;

    stk501xx_phase_reset(stk);
    return (ssize_t)result;
}

static DEVICE_ATTR(enable, 0644, stk_enable_show, stk_enable_store);
static DEVICE_ATTR(value, 0444, stk_value_show, NULL);
static DEVICE_ATTR(temp, 0444, stk_temp_show, NULL);
static DEVICE_ATTR(flag, 0444, stk_flag_show, NULL);
static DEVICE_ATTR(allreg, 0400, stk_allreg_show, NULL);
static DEVICE_ATTR(chipinfo, 0444, stk_chipinfo_show, NULL);
static DEVICE_ATTR(phcali, 0400, stk_phase_cali, NULL);

static struct attribute *stk_attribute_sar[] =
{
    &dev_attr_enable.attr,
    &dev_attr_value.attr,
    &dev_attr_temp.attr,
    &dev_attr_flag.attr,
    &dev_attr_allreg.attr,
    &dev_attr_chipinfo.attr,
    &dev_attr_phcali.attr,
    NULL
};

struct attribute_group stk_attribute_sar_group =
{
    .name = STK501XX_NAME,
    .attrs = stk_attribute_sar,
};

static struct stk501xx_platform_data stk_plat_data =
{
    .interrupt_int1_pin     = 117,
    .phase_use_flag         = 0,
};

#ifdef STK_SENSORS_DEV
/* SAR information read by HAL */
static struct sensors_classdev stk_cdev = {
    .name = "stk501xx",
    .vendor = "Sensortek",
    .version = 1,
    .type = 5013,
    .max_range = "1",
    .resolution = "1",
    .sensor_power = "1",
    .min_delay = 0,
    .max_delay = 0,
    .delay_msec = 16,
    .fifo_reserved_event_count = 0,
    .fifo_max_event_count = 0,
    .enabled = 0,
    .max_latency = 0,
    .flags = 0, /* SENSOR_FLAG_CONTINUOUS_MODE */
    .sensors_enable = NULL,
    .sensors_poll_delay = NULL,
    .sensors_enable_wakeup = NULL,
    .sensors_set_latency = NULL,
    .sensors_flush = NULL,
    .sensors_calibrate = NULL,
    .sensors_write_cal_params = NULL,
};

/*
 * @brief: The handle for enable and disable sensor.
 *          include/linux/sensors.h
 *
 * @param[in] *sensors_cdev: struct sensors_classdev
 * @param[in] enabled:
 */
static int stk_cdev_sensors_enable(struct sensors_classdev *sensors_cdev,
                                   unsigned int enabled)
{
    struct stk501xx_wrapper *stk_wrapper = container_of(sensors_cdev, stk501xx_wrapper, sar_cdev);
    struct stk_data *stk = &stk_wrapper->stk;

    if (0 == enabled) {
        stk501xx_set_enable(stk, 0);
    } else if (1 == enabled) {
        stk501xx_set_enable(stk, 1);
    } else {
        STK_SAR_ERR("Invalid vlaue of input, input=%d", enabled);
        return -EINVAL;
    }

    return 0;
}

/*
 * @brief: The handle for set the sensor polling delay time.
 *          include/linux/sensors.h
 *
 * @param[in] *sensors_cdev: struct sensors_classdev
 * @param[in] delay_msec:
 */
static int stk_cdev_sensors_poll_delay(struct sensors_classdev *sensors_cdev,
                                       unsigned int delay_msec)
{
#ifdef STK_INTERRUPT_MODE
    /* do nothing */
#elif defined STK_POLLING_MODE
    struct stk501xx_wrapper *stk_wrapper = container_of(sensors_cdev, stk501xx_wrapper, sar_cdev);
    struct stk_data *stk = &stk_wrapper->stk;

    stk->stk_timer_info.interval_time = delay_msec * 1000;
#endif /* STK_INTERRUPT_MODE, STK_POLLING_MODE */

    STK_SAR_LOG("stk_cdev_sensors_poll_delay ms=%d", delay_msec);
    return 0;
}

/*
 * @brief:
 *          include/linux/sensors.h
 *
 * @param[in] *sensors_cdev: struct sensors_classdev
 * @param[in] enable:
 */
static int stk_cdev_sensors_enable_wakeup(struct sensors_classdev *sensors_cdev,
        unsigned int enable)
{
    STK_SAR_LOG("enable=%d", enable);
    return 0;
}

/*
 * @brief: Flush sensor events in FIFO and report it to user space.
 *          include/linux/sensors.h
 *
 * @param[in] *sensors_cdev: struct sensors_classdev
 */
static int stk_cdev_sensors_flush(struct sensors_classdev *sensors_cdev)
{
    STK_SAR_LOG("stk_cdev_sensors_flush");
    return 0;
}
#endif // STK_SENSORS_DEV

/*
 * @brief: File system setup for accel and any motion
 *
 * @param[in/out] stk: struct stk_data *
 *
 * @return: Success or fail
 *          0: Success
 *          others: Fail
 */
static int stk_input_setup(stk501xx_wrapper *stk_wrapper)
{
    int err = 0;

    /* input device: setup for sar */
    stk_wrapper->input_dev = input_allocate_device();
    if (!stk_wrapper->input_dev) {
        STK_SAR_ERR("input_allocate_device for sar failed");
        return -ENOMEM;
    }

    stk_wrapper->input_dev->name =  "sar_sensor";
    stk_wrapper->input_dev->id.bustype = BUS_I2C;
    input_set_capability(stk_wrapper->input_dev, EV_ABS, ABS_DISTANCE);
    stk_wrapper->input_dev->dev.parent = &stk_wrapper->i2c_mgr.client->dev;
    input_set_drvdata(stk_wrapper->input_dev, stk_wrapper);

    err = input_register_device(stk_wrapper->input_dev);
    if (err) {
        STK_SAR_ERR("Unable to register input device: %s", stk_wrapper->input_dev->name);
        input_free_device(stk_wrapper->input_dev);
        return err;
    }

    return 0;
}

/*
 * @brief:
 *
 * @param[in/out] stk: struct stk_data *
 *
 * @return:
 *      0: Success
 *      others: Fail
 */
static int stk_init_qualcomm(stk501xx_wrapper *stk_wrapper)
{
    int err = 0;

    if (stk_input_setup(stk_wrapper)) {
        return -1;
    }

    /* sysfs: create file system */
    err = sysfs_create_group(&stk_wrapper->i2c_mgr.client->dev.kobj,
                             &stk_attribute_sar_group);
    if (err) {
        STK_SAR_ERR("Fail in sysfs_create_group, err=%d", err);
        goto err_sysfs_creat_group;
    }

#ifdef STK_SENSORS_DEV
    stk_wrapper->sar_cdev = stk_cdev;
    stk_wrapper->sar_cdev.name = "stk501xx";
    stk_wrapper->sar_cdev.sensors_enable = stk_cdev_sensors_enable;
    stk_wrapper->sar_cdev.sensors_poll_delay = stk_cdev_sensors_poll_delay;
    stk_wrapper->sar_cdev.sensors_enable_wakeup = stk_cdev_sensors_enable_wakeup;
    stk_wrapper->sar_cdev.sensors_flush = stk_cdev_sensors_flush;
    err = sensors_classdev_register(&stk_wrapper->input_dev->dev, &stk_wrapper->sar_cdev);
#endif // STK_SENSORS_DEV

    if (err) {
        STK_SAR_ERR("Fail in sensors_classdev_register, err=%d", err);
        goto err_sensors_classdev_register;
    }

    return 0;

err_sensors_classdev_register:
    sysfs_remove_group(&stk_wrapper->i2c_mgr.client->dev.kobj, &stk_attribute_sar_group);
err_sysfs_creat_group:
    input_unregister_device(stk_wrapper->input_dev);   /* MU300: registered, so unregistered (it frees it) */
    stk_wrapper->input_dev = NULL;
    return -1;
}

/*
 * @brief: Exit qualcomm related settings safely.
 *
 * @param[in/out] stk: struct stk_data *
 */
static void stk_exit_qualcomm(struct stk501xx_wrapper *stk_wrapper)
{
#ifdef STK_SENSORS_DEV
    sensors_classdev_unregister(&stk_wrapper->sar_cdev);
#endif // STK_SENSORS_DEV
    sysfs_remove_group(&stk_wrapper->i2c_mgr.client->dev.kobj,
                       &stk_attribute_sar_group);
    input_unregister_device(stk_wrapper->input_dev);   /* MU300: it frees it; no input_free_device() after */
    stk_wrapper->input_dev = NULL;
}

#if defined STK_INTERRUPT_MODE || defined STK_POLLING_MODE
void stk_report_sar_data(struct stk_data* stk)
{
    stk501xx_wrapper *stk_wrapper = container_of(stk, stk501xx_wrapper, stk);
    int i = 0;
    u8 is_change = 0;
    u8 nf_flag = 0;

    if (!stk_wrapper->input_dev) {
        STK_SAR_ERR("No input device for sar data");
        return;
    }

    for (i = 0; i < 8; i ++) {
        if (((stk->phase_use_flag >> i) & 0x01) == 0) {
            // STK_SAR_ERR("stk_report_sar_data:: phase %d not used", i);
            continue;
        }

        nf_flag = is_change = 0;
        is_change |= stk->state_change[i];

        STK_SAR_ERR("stk_report_sar_data:: change ph[%d] =%d,(%d)", i, stk->state_change[i], is_change);

        if (STK_SAR_NEAR_BY == stk->last_nearby[i]) {
            nf_flag = (i + 1);
        } else if (STK_SAR_FAR_AWAY == stk->last_nearby[i]) {
            nf_flag = ( i + 1 ) * 10 ;
        }

        STK_SAR_ERR("stk_report_sar_data:: nf_flag ph[%d] =%d,(%d)", i, stk->last_nearby[i], nf_flag);

        if (is_change != 0) {
            input_report_abs(stk_wrapper->input_dev, ABS_DISTANCE, nf_flag);
            input_sync(stk_wrapper->input_dev);
        }
    }
}
#endif

#ifdef CONFIG_OF
/*
 * @brief: Parse data in device tree
 *
 * @param[in] dev: struct device *
 * @param[in/out] pdata: struct stk501xx_platform_data *
 *
 * @return: Success or fail
 *          0: Success
 *          others: Fail
 */
static int stk_parse_dt(struct device *dev,
                        struct stk501xx_platform_data *pdata)
{
    struct device_node *np = dev->of_node;
    struct gpio_desc *irq_gpio;
    uint32_t val;

    /* MU300: the line's number for the legacy GPIO calls of common_gpio_qualcomm.c (of_get_named_gpio_flags()
     * is gone from mainline): looked up as a descriptor and handed back at once */
    irq_gpio = gpiod_get(dev, "stk501xx,irq", GPIOD_ASIS);
    if (IS_ERR(irq_gpio)) {
        pdata->interrupt_int1_pin = PTR_ERR(irq_gpio);
    } else {
        pdata->interrupt_int1_pin = desc_to_gpio(irq_gpio);
        gpiod_put(irq_gpio);
    }
    if (pdata->interrupt_int1_pin < 0) {
        STK_SAR_ERR("Unable to read stk501xx,irq-gpio");
#ifdef STK_INTERRUPT_MODE
        return pdata->interrupt_int1_pin;
#else
        return 0;
#endif
    }

    val = of_property_read_u32(np, "stk501xx,phase_use_flag", &pdata->phase_use_flag);
    if (val != 0) {
        STK_SAR_ERR("Unable to read stk501xx,phase_use_flag %d", val);
        pdata->phase_use_flag = 7;
    } else {
        STK_SAR_ERR("stk501xx,phase_use_flag = %d", pdata->phase_use_flag);
    }

    return 0;
}
#else
static int stk_parse_dt(struct device *dev,
                        struct stk501xx_platform_data *pdata)
{
    return -ENODEV
}
#endif /* CONFIG_OF */

/*
 * @brief: Get platform data
 *
 * @param[in/out] stk: struct stk_data *
 *
 * @return: Success or fail
 *          0: Success
 *          others: Fail
 */
static int get_platform_data(stk501xx_wrapper *stk_wrapper)
{
    int err = 0;
    struct i2c_client *client = stk_wrapper->i2c_mgr.client;
    struct stk501xx_platform_data *stk_platdata;

    if (client->dev.of_node) {
        STK_SAR_FUN();

        stk_platdata = devm_kzalloc(&client->dev,
                                    sizeof(struct stk501xx_platform_data), GFP_KERNEL);
        if (!stk_platdata) {
            STK_SAR_ERR("Failed to allocate memory");
            return -ENOMEM;
        }

        err = stk_parse_dt(&client->dev, stk_platdata);
        if (err) {
            STK_SAR_ERR("stk_parse_dt err=%d", err);
            return err;
        }
    } else {
        if (NULL != client->dev.platform_data) {
            STK_SAR_ERR("probe with platform data");
            stk_platdata = client->dev.platform_data;
        } else {
            STK_SAR_ERR("probe with private platform data");
            stk_platdata = &stk_plat_data;
        }
    }

#ifdef STK_INTERRUPT_MODE
    stk_wrapper->stk.gpio_info.int_pin = stk_platdata->interrupt_int1_pin;
    STK_SAR_ERR("int_pin=%d", stk_wrapper->stk.gpio_info.int_pin);
#endif /* STK_INTERRUPT_MODE */

    stk_wrapper->stk.phase_use_flag = stk_platdata->phase_use_flag;
    return 0;
}

static struct class sar_sensor_class = {
    .name = "sarsensor",
};

static ssize_t delay_show(const struct class *class,
        const struct class_attribute *attr,
        char *buf)
{
    STK_SAR_ERR("delay_show");
    return snprintf(buf, 8, "%d\n", 200);
}

static ssize_t delay_store(const struct class *class,
        const struct class_attribute *attr,
        const char *buf, size_t count)
{
    STK_SAR_ERR("delay_store");
    return count;
}
static CLASS_ATTR_RW(delay);

static ssize_t enable_show(const struct class *class,
        const struct class_attribute *attr,
        char *buf)
{
    ssize_t ret = -ENODEV;

    /* MU300: the device only while it is there (stk_i2c_remove() clears the pointer before it frees it) */
    mutex_lock(&stk_class_lock);
    if (stk501xx_wrapper_ptr)
        ret = scnprintf(buf, PAGE_SIZE, "enable = %d\n", stk501xx_wrapper_ptr->stk.enabled);
    mutex_unlock(&stk_class_lock);
    return ret;
}

static ssize_t enable_store(const struct class *class,
        const struct class_attribute *attr,
        const char *buf, size_t count)
{
    unsigned int data;
    int error;

    error = kstrtouint(buf, 10, &data);
    if (error)
        return error;
    if (data > 1)
        return -EINVAL;
    mutex_lock(&stk_class_lock);
    if (!stk501xx_wrapper_ptr) {
        mutex_unlock(&stk_class_lock);
        return -ENODEV;
    }
    stk501xx_set_enable(&stk501xx_wrapper_ptr->stk, data);
    mutex_unlock(&stk_class_lock);
    return count;
}
static CLASS_ATTR_RW(enable);

static ssize_t chip_info_show(const struct class *class,
        const struct class_attribute *attr,
        char *buf)
{
    STK_SAR_ERR("chip_info_show, chip_info = %s\n", chip_info);
    return snprintf(buf, 25, "%s", chip_info);
}
static CLASS_ATTR_RO(chip_info);

static ssize_t status_show(const struct class *class,
        const struct class_attribute *attr,
        char *buf)
{
    uint32_t prox_flag = 0;
    stk_data *stk;

    mutex_lock(&stk_class_lock);
    if (!stk501xx_wrapper_ptr) {
        mutex_unlock(&stk_class_lock);
        return -ENODEV;
    }
    stk = &stk501xx_wrapper_ptr->stk;
    stk_read_prox_flag(stk, &prox_flag);
    stk501xx_read_sar_data(stk, prox_flag);
    mutex_unlock(&stk_class_lock);
    return scnprintf(buf, PAGE_SIZE, "flag=0x%x\n", prox_flag);
}
static CLASS_ATTR_RO(status);

static ssize_t batch_show(const struct class *class,
        const struct class_attribute *attr,
        char *buf)
{
    STK_SAR_ERR("batch_show sar sensor");
    return snprintf(buf, 64, "200\n");
}

static ssize_t batch_store(const struct class *class,
        const struct class_attribute *attr,
        const char *buf, size_t count)
{
    STK_SAR_ERR("batch_store sar sensor");
    return count;
}
static CLASS_ATTR_RW(batch);

static ssize_t flush_show(const struct class *class,
        const struct class_attribute *attr,
        char *buf)
{
    STK_SAR_ERR("flush_show sar sensor");
    return snprintf(buf, 64, "0\n");
}

static ssize_t flush_store(const struct class *class,
        const struct class_attribute *attr,
        const char *buf, size_t count)
{
    STK_SAR_ERR("flush_store sar sensor");
    return count;
}
static CLASS_ATTR_RW(flush);

/*
 * @brief: Probe function for i2c_driver.
 *
 * @param[in] client: struct i2c_client *
 * @param[in] stk_bus_ops: const struct stk_bus_ops *
 *
 * @return: Success or fail
 *          0: Success
 *          others: Fail
 */
int stk_i2c_probe(struct i2c_client *client, struct common_function *common_fn)
{
    int err = 0;
    stk501xx_wrapper *stk_wrapper;
    struct stk_data *stk;

    STK_SAR_LOG("STK_HEADER_VERSION: %s ", STK_HEADER_VERSION);
    STK_SAR_LOG("STK_C_VERSION: %s ", STK_C_VERSION);
    STK_SAR_LOG("STK_DRV_I2C_VERSION: %s ", STK_DRV_I2C_VERSION);
    STK_SAR_LOG("STK_QUALCOMM_VERSION: %s ", STK_QUALCOMM_VERSION);

    if (NULL == client) {
        return -ENOMEM;
    } else if (!common_fn) {
        STK_SAR_ERR("cannot get common function. EXIT");
        return -EIO;
    }

    if (!i2c_check_functionality(client->adapter, I2C_FUNC_I2C)) {
        err = i2c_get_functionality(client->adapter);
        STK_SAR_ERR("i2c_check_functionality error, functionality=0x%x", err);
        return -EIO;
    }

    snprintf(chip_info, sizeof(chip_info), "%s", "sensortek");

    /* kzalloc: allocate memory and set to zero. */
    stk_wrapper = kzalloc(sizeof(stk501xx_wrapper), GFP_KERNEL);
    if (!stk_wrapper) {
        STK_SAR_ERR("memory allocation error");
        return -ENOMEM;
    }

    stk = &stk_wrapper->stk;
    if (!stk) {
        printk(KERN_ERR "%s: failed to allocate stk3a8x_data\n", __func__);
        return -ENOMEM;
    }

    stk_wrapper->i2c_mgr.client = client;
    stk_wrapper->i2c_mgr.addr_type = ADDR_16BIT;
    stk->bops   = common_fn->bops;
    stk->tops   = common_fn->tops;
    stk->gops   = common_fn->gops;
    stk->sops   = common_fn->sops;
    stk->sar_report_cb = stk_report_sar_data;
    i2c_set_clientdata(client, stk_wrapper);
    mutex_init(&stk_wrapper->i2c_mgr.lock);

    stk->bus_idx = stk->bops->init(&stk_wrapper->i2c_mgr);
    if (stk->bus_idx < 0) {
        err = -ENOMEM;
        goto err_free_mem;
    }

    if (get_platform_data(stk_wrapper)){
        err = -ENOMEM;
        goto err_bus;
    }

    /* registers the interrupt (stk_register_queue()) */
    err = stk501xx_init_client(stk);
    if (err < 0) {
        STK_SAR_ERR("stk501xx_init_client failed\n");
        err = -ENOMEM;
        goto err_irq;
    }

    if (stk_init_qualcomm(stk_wrapper)) {
        STK_SAR_ERR("stk_init_qualcomm failed");
        err = -ENOMEM;
        goto err_irq;
    }

    /*
     * MU300: ZTE's boardtest hook (CONFIG_VENDOR_ZTE_MISC_COMMON, is_sar1_exist) is not built: there is no zte_misc
     * on mainline. The class (one sensor: one class) and its files, the device reached through
     * stk501xx_wrapper_ptr, set here and cleared before the device goes.
     */
    err = class_register(&sar_sensor_class);
    if (err < 0) {
        STK_SAR_ERR("Create fsys class failed  err = %d", err);
        goto err_qualcomm;
    }
    {
        const struct class_attribute *attrs[] = {
            &class_attr_delay, &class_attr_enable, &class_attr_chip_info,
            &class_attr_batch, &class_attr_flush, &class_attr_status,
        };
        int a;

        for (a = 0; a < ARRAY_SIZE(attrs); a++) {
            err = class_create_file(&sar_sensor_class, attrs[a]);
            if (err < 0) {
                STK_SAR_ERR("Create class file failed  err = %d", err);
                goto err_class;
            }
        }
    }
    mutex_lock(&stk_class_lock);
    stk501xx_wrapper_ptr = stk_wrapper;
    mutex_unlock(&stk_class_lock);

    STK_SAR_LOG("Success");
    return 0;

err_class:
    /* (its files go with it) */
    class_unregister(&sar_sensor_class);
err_qualcomm:
    stk_exit_qualcomm(stk_wrapper);
err_irq:
#ifdef STK_INTERRUPT_MODE
    STK_GPIO_IRQ_REMOVE(stk, &stk->gpio_info);
#elif defined STK_POLLING_MODE
    STK_TIMER_REMOVE(stk, &stk->stk_timer_info);
#endif /* STK_INTERRUPT_MODE, STK_POLLING_MODE */
err_bus:
    stk->bops->remove(&stk_wrapper->i2c_mgr);
err_free_mem:
    STK_SAR_ERR("err_free_mem err = %d", err);
    mutex_destroy(&stk_wrapper->i2c_mgr.lock);
    kfree(stk_wrapper);   /* MU300: the wrapper is the allocation (stk is inside it) */
    return err;
}

/*
 * @brief: Remove function for i2c_driver.
 *
 * @param[in] client: struct i2c_client *
 *
 * @return: 0
 */
int stk_i2c_remove(struct i2c_client *client)
{
    stk501xx_wrapper *stk_wrapper = i2c_get_clientdata(client);
    struct stk_data *stk = &stk_wrapper->stk;

    /* MU300: in the reverse order of probe - the interrupt and its work first (they use the input device and the
     * data), then the class files (cleared pointer, files gone), then the device's files and input device */
#ifdef STK_INTERRUPT_MODE
    STK_GPIO_IRQ_REMOVE(stk, &stk->gpio_info);
#elif defined STK_POLLING_MODE
    STK_TIMER_REMOVE(stk, &stk->stk_timer_info);
#endif /* STK_INTERRUPT_MODE, STK_POLLING_MODE */
    mutex_lock(&stk_class_lock);
    stk501xx_wrapper_ptr = NULL;
    mutex_unlock(&stk_class_lock);
    class_unregister(&sar_sensor_class);
    stk_exit_qualcomm(stk_wrapper);
    stk->bops->remove(&stk_wrapper->i2c_mgr);
    mutex_destroy(&stk_wrapper->i2c_mgr.lock);
    kfree(stk_wrapper);
    return 0;
}

int stk501xx_suspend(struct device* dev)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    struct stk_data *stk = &stk_wrapper->stk;

    if(stk_wrapper != NULL) {
        if (stk->enabled) {
            stk501xx_set_enable(stk, 0);
            stk->last_enable = true;
        } else
            stk->last_enable = false;
    }

    return 0;
}

int stk501xx_resume(struct device* dev)
{
    stk501xx_wrapper *stk_wrapper = dev_get_drvdata(dev);
    struct stk_data *stk = &stk_wrapper->stk;

    if (stk_wrapper != NULL) {
        if (stk->last_enable)
            stk501xx_set_enable(stk, 1);

        stk->last_enable = false;
    }
    return 0;
}

#ifdef CONFIG_OF
static struct of_device_id stk501xx_match_table[] =
{
    { .compatible = "stk,stk501xx", },
    {}
};
#endif /* CONFIG_OF */

/*
 * @brief: Proble function for i2c_driver.
 *
 * @param[in] client: struct i2c_client *
 * @param[in] id: struct i2c_device_id *
 *
 * @return: Success or fail
 *          0: Success
 *          others: Fail
 */
static int stk501xx_i2c_probe(struct i2c_client* client)
{
    struct common_function common_fn = {
        .bops = &stk_i2c_bops,
        .tops = &stk_t_ops,
        .gops = &stk_g_ops,
        .sops = &stk_s_ops,
    };
    return stk_i2c_probe(client, &common_fn);
}

/*
 * @brief: Remove function for i2c_driver.
 *
 * @param[in] client: struct i2c_client *
 *
 * @return: 0
 */
static void stk501xx_i2c_remove(struct i2c_client* client)
{
    stk_i2c_remove(client);
}

/**
 * @brief:
 */
static int __maybe_unused stk501xx_i2c_detect(struct i2c_client* client, struct i2c_board_info* info)
{
    strcpy(info->type, STK501XX_NAME);
    return 0;
}

#ifdef CONFIG_PM_SLEEP
/*
 * @brief: Suspend function for dev_pm_ops.
 *
 * @param[in] dev: struct device *
 *
 * @return: 0
 */
static int stk501xx_i2c_suspend(struct device* dev)
{
    return stk501xx_suspend(dev);
}

/*
 * @brief: Resume function for dev_pm_ops.
 *
 * @param[in] dev: struct device *
 *
 * @return: 0
 */
static int stk501xx_i2c_resume(struct device* dev)
{
    return stk501xx_resume(dev);
}

static const struct dev_pm_ops stk501xx_pm_ops = {
    .suspend = stk501xx_i2c_suspend,
    .resume = stk501xx_i2c_resume,
};
#endif /* CONFIG_PM_SLEEP */

#ifdef CONFIG_ACPI
static const struct acpi_device_id stk501xx_acpi_id[] = {
    {"STK501XX", 0},
    {}
};
MODULE_DEVICE_TABLE(acpi, stk501xx_acpi_id);
#endif /* CONFIG_ACPI */

static const struct i2c_device_id stk501xx_i2c_id[] = {
    {STK501XX_NAME, 0},
    {}
};

MODULE_DEVICE_TABLE(i2c, stk501xx_i2c_id);

static struct i2c_driver stk501xx_i2c_driver = {
    .probe = stk501xx_i2c_probe,
    .remove = stk501xx_i2c_remove,
    /* MU300: no .detect/.class: the device tree instantiates the sensor, no other bus is probed for it */
    .id_table = stk501xx_i2c_id,
    .driver = {
        .owner = THIS_MODULE,
        .name = STK501XX_NAME,
#ifdef CONFIG_PM_SLEEP
        .pm = &stk501xx_pm_ops,
#endif
#if defined(CONFIG_ACPI) && !defined(STK_SPREADTRUM)
        .acpi_match_table = ACPI_PTR(stk501xx_acpi_id),
#endif /* CONFIG_ACPI */
#if defined(CONFIG_OF) || defined(STK_SPREADTRUM)
        .of_match_table = stk501xx_match_table,
#endif /* CONFIG_OF */
    }
};

module_i2c_driver(stk501xx_i2c_driver);

MODULE_AUTHOR("Sensortek");
MODULE_DESCRIPTION("stk501xx sar driver");
MODULE_LICENSE("GPL");
//MODULE_VERSION(STK_QUALCOMM_VERSION);