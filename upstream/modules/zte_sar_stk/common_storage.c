/*
 *  common_storage.c - Linux kernel modules for sensortek stk5xxx
 *  accelerometer sensor (Common function)
 *
 *  Copyright (C) 2019 STK, sensortek Inc.
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 */

#include <linux/fs.h>
#include <asm/uaccess.h>
#include "common_define.h"

int init_storage(void)
{
    return 0;
}

int write_to_storage(char *name, uint8_t *w_buf, int buf_size)
{
    // struct file  *cali_file = NULL;
    // mm_segment_t fs;
    // loff_t pos;
    // int err;
    // cali_file = filp_open(name, O_CREAT | O_RDWR, 0666);

    // if (IS_ERR(cali_file))
    // {
    //     err = PTR_ERR(cali_file);
    //     printk(KERN_ERR "%s: filp_open error!err=%d,path=%s\n", __func__, err, name);
    //     return -1;
    // }
    // else
    // {
    //     fs = get_fs();
    //     set_fs(KERNEL_DS);
    //     pos = 0;
    //     vfs_write(cali_file, w_buf, buf_size, &pos);
    //     set_fs(fs);
    // }

    // filp_close(cali_file, NULL);
    return 0;
}

int read_from_storage(char *name, uint8_t *r_buf, int buf_size)
{
    // struct file  *cali_file = NULL;
    // mm_segment_t fs;
    // loff_t pos;
    // int err;
    // cali_file = filp_open(name, O_CREAT | O_RDWR, 0644);

    // if (IS_ERR(cali_file))
    // {
    //     err = PTR_ERR(cali_file);
    //     printk(KERN_ERR "%s: filp_open error!err=%d,path=%s\n", __func__, err, name);
    //     return -1;
    // }
    // else
    // {
    //     fs = get_fs();
    //     set_fs(KERNEL_DS);
    //     pos = 0;
    //     vfs_read(cali_file, r_buf, buf_size, &pos);
    //     set_fs(fs);
    // }

    // filp_close(cali_file, NULL);
    return 0;
}

int remove_storage(void)
{
    return 0;
}

const struct stk_storage_ops stk_s_ops =
{
    .init_storage           = init_storage,
    .write_to_storage       = write_to_storage,
    .read_from_storage      = read_from_storage,
    .remove                 = remove_storage,
};
