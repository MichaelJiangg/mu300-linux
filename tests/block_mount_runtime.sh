#!/bin/sh
# Run ONLY in a disposable OpenWrt container, with the patched APK at /in/block.apk.
set -eu
[ "${MU300_BLOCK_TEST_CONTAINER:-}" = 1 ] || { echo 'container opt-in required' >&2; exit 2; }
apk update >/dev/null
apk add --allow-untrusted /in/block.apk >/dev/null
apk add e2fsprogs coreutils-timeout >/dev/null
apk list --installed block-mount | grep -F '16718b6e-r100'
test -x /sbin/block
test -s /lib/libblkid-tiny.so
test -x /etc/init.d/fstab
disk=/dev/sd-mu300-test.img
fifo=/dev/sdiag-mu300-test
channel=/dev/sdiom-mu300-test
for p in "$disk" "$fifo" "$channel"; do
    [ ! -e "$p" ] && [ ! -L "$p" ] || exit 2
done
trap 'rc=$?; rm -f "$disk" "$fifo" "$channel" /tmp/mu300-block-info /tmp/mu300-block-detect; exit "$rc"' EXIT
mkfifo "$fifo"
ln -s /dev/zero "$channel"
dd if=/dev/zero of="$disk" bs=1M count=0 seek=16 2>/dev/null
[ -f "$disk" ] && [ ! -b "$disk" ] && [ ! -c "$disk" ]
mkfs.ext4 -q -F -L MU300_TEST "$disk"
# An unsafe probe hangs on the FIFO even when a specific disk argument is used.
timeout 5 /sbin/block info > /tmp/mu300-block-info
grep -q 'LABEL="MU300_TEST".*TYPE="ext4"' /tmp/mu300-block-info
! grep -E 'sdiag-mu300|sdiom-mu300' /tmp/mu300-block-info
# The explicit-info path only prints block nodes (not regular-file fixtures),
# but must still finish its initial full scan in the presence of the FIFO.
timeout 5 /sbin/block info "$disk" >/dev/null
timeout 5 /sbin/block detect > /tmp/mu300-block-detect
grep -q '/mnt/sd-mu300-test.img' /tmp/mu300-block-detect
! grep -E 'sdiag-mu300|sdiom-mu300' /tmp/mu300-block-detect
echo 'block-mount runtime: APK, normal ext4 discovery and communication/FIFO filtering passed'
