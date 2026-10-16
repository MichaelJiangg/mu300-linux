/* No real device is opened or changed by these tests. */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
static mode_t fixture_mode;
static const char *fixture_subsystem;
static int fixture_exists = 1, reads;
static int mock_stat(const char *path, struct stat *st)
{
    (void)path;
    if (!fixture_exists) return -1;
    st->st_mode = fixture_mode;
    st->st_rdev = makedev(250, 7);
    return 0;
}
static ssize_t mock_readlink(const char *path, char *buf, size_t len)
{
    reads++;
    assert(!strcmp(path, "/sys/dev/char/250:7/subsystem"));
    if (!fixture_subsystem) return -1;
    size_t n = strlen(fixture_subsystem);
    if (n > len) n = len;
    memcpy(buf, fixture_subsystem, n);
    return n;
}
#define stat(path, st) mock_stat(path, st)
#define readlink mock_readlink
#include "../openwrt/block-probe-guard.h"
#undef stat
#undef readlink
int main(void)
{
    fixture_mode = S_IFBLK; assert(mu300_probe_allowed("/dev/mmcblk1p1"));
    assert(mu300_probe_allowed("/dev/sda1"));
    fixture_mode = S_IFREG; assert(mu300_probe_allowed("/mnt/swapfile"));
    fixture_mode = S_IFDIR; assert(!mu300_probe_allowed("/dev/sd-directory"));
    fixture_mode = S_IFIFO; assert(!mu300_probe_allowed("/dev/sdiag-fifo"));
    fixture_mode = S_IFSOCK; assert(!mu300_probe_allowed("/dev/sd-socket"));
    assert(!reads);
    fixture_mode = S_IFCHR;
    fixture_subsystem = "../../../../class/tty";
    assert(!mu300_probe_allowed("/dev/sdiag"));
    assert(!mu300_probe_allowed("/dev/ubi0_0")); /* name alone is not trust */
    fixture_subsystem = "../../../../class/spipe";
    assert(!mu300_probe_allowed("/dev/sdiom"));
    fixture_subsystem = NULL; assert(!mu300_probe_allowed("/dev/slog"));
    fixture_subsystem = "../../../../class/ubi";
    assert(mu300_probe_allowed("/dev/ubi0_0"));
    fixture_exists = 0; assert(!mu300_probe_allowed("/dev/missing"));
    puts("block probe guard: 12 checks passed");
    return 0;
}
