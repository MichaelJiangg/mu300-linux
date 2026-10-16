#!/bin/sh
# Run in a disposable OpenWrt container with the repository mounted read-only.
# No devices, network, services or boot metadata are accessed.
set -eu
task_tmp=$(mktemp -d /tmp/mu300-vendor-copy.XXXXXX)
trap 'rm -rf "$task_tmp"' EXIT
export MU300_LIB=1 MU300_DISK="$task_tmp/disk"
. "${1:?path to mu300-update}"
mkdir -p "$task_tmp/old/firmware" "$task_tmp/new/firmware" "$task_tmp/outside"
printf vendor > "$task_tmp/old/firmware/wcnmodem.bin"
printf board > "$task_tmp/old/firmware/wifi_board_config.ini"
printf image > "$task_tmp/new/firmware/regulatory.db"
busybox cp -an "$task_tmp/old/firmware/." "$task_tmp/new/firmware/" || true
[ ! -e "$task_tmp/new/firmware/wcnmodem.bin" ]
copy_missing "$task_tmp/old" "$task_tmp/new"
[ "$(cat "$task_tmp/new/firmware/wcnmodem.bin")" = vendor ]
[ "$(cat "$task_tmp/new/firmware/wifi_board_config.ini")" = board ]
[ "$(cat "$task_tmp/new/firmware/regulatory.db")" = image ]
mkdir -p "$task_tmp/old/link/subdir"
printf unsafe > "$task_tmp/old/link/subdir/file"
ln -s "$task_tmp/outside" "$task_tmp/new/link"
copy_missing "$task_tmp/old" "$task_tmp/new"
[ ! -e "$task_tmp/outside/subdir" ]
mkdir "$task_tmp/failure"
cp() { return 1; }
if copy_missing "$task_tmp/old/firmware" "$task_tmp/failure"; then
    echo 'copy error was hidden' >&2
    exit 1
fi
echo 'PASS: real OpenWrt BusyBox reproduces old loss; firmware merge, image retention, symlink guard and copy failure pass'
