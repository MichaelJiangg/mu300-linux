/* SPDX-License-Identifier: LGPL-2.1-or-later
 * /dev/sd* on Unisoc also contains sdiag/sdiom/sd* communication channels.
 * Reject them BEFORE probe_path() opens/reads anything. Keep ordinary disk
 * nodes, regular files (swapfiles), and kernel-confirmed UBI character nodes.
 */
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

static bool mu300_probe_allowed(const char *path)
{
    struct stat st;
    char sysfs[96], subsystem[256];
    ssize_t len;
    const char *name;

    if (stat(path, &st))
        return false;
    if (S_ISBLK(st.st_mode) || S_ISREG(st.st_mode))
        return true;
    if (!S_ISCHR(st.st_mode))
        return false;

    snprintf(sysfs, sizeof(sysfs), "/sys/dev/char/%u:%u/subsystem",
             major(st.st_rdev), minor(st.st_rdev));
    len = readlink(sysfs, subsystem, sizeof(subsystem) - 1);
    if (len <= 0 || len >= (ssize_t)sizeof(subsystem) - 1)
        return false;
    subsystem[len] = '\0';
    name = strrchr(subsystem, '/');
    return name && !strcmp(name + 1, "ubi");
}
