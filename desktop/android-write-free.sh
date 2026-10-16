#!/system/bin/sh
# Desktop has validated both GPT copies and selected an unallocated range.
# Android keeps userdata mounted; never request BLKRRPART on its parent disk.
set -eu
set -o pipefail
P=${MU300_PAYLOAD_DIR:?};T=${MU300_INSTALL_TMP:?}
. "$P/desktop-settings.env"
. "$P/android-loop.sh"
# BusyBox's losetup lacks a size-limit option. Use Android Toybox explicitly;
# PATH in the installer intentionally points at BusyBox for other applets.
[ -x /system/bin/losetup ] && /system/bin/losetup --help 2>&1 | grep -q -- '-S' || {
    echo 'Android losetup with -S (bounded loop) is required; nothing written' >&2; exit 1;
}
disk=${1:?disk};cid=${2:?cid};total=${3:?sectors};start=${4:?start};need=${5:?size}
want=${6:?image checksum};front=${7:?GPT front sectors};tail=${8:?GPT backup start}
node=${disk##*/}
case "$disk" in /dev/block/mmcblk[0-9]) ;; *) exit 1 ;; esac
[ -b "$disk" ] || { echo 'eMMC block device required' >&2; exit 1; }
for value in "$total" "$start" "$need" "$front" "$tail"; do
    case "$value" in ''|*[!0-9]*) exit 1 ;; esac
done
[ "$(cat /sys/class/block/$node/device/cid)" = "$cid" ]
[ "$(cat /sys/class/block/$node/size)" = "$total" ]
[ "$front" -ge 3 ] && [ "$front" -le 4096 ]
[ "$tail" -ge "$((total-4096))" ] && [ "$tail" -lt "$total" ]
[ "$start" -ge "$front" ] && [ "$need" -ge 4194304 ]
[ "$((start%2048))" = 0 ] && [ "$((need%2048))" = 0 ]
[ "$((start+need))" -le "$tail" ]
for region in before new; do
    [ "$(stat -c %s "$P/gpt-$region-first.bin")" = "$((front*512))" ]
    [ "$(stat -c %s "$P/gpt-$region-last.bin")" = "$(((total-tail)*512))" ]
done
check_gpt() {
    dd if="$disk" of="$T/gpt-check-first.bin" bs=512 count="$front" 2>/dev/null
    dd if="$disk" of="$T/gpt-check-last.bin" bs=512 skip="$tail" count="$((total-tail))" 2>/dev/null
    cmp -s "$P/gpt-$1-first.bin" "$T/gpt-check-first.bin" &&
        cmp -s "$P/gpt-$1-last.bin" "$T/gpt-check-last.bin"
}
check_gpt before || { echo 'GPT changed; no free-space write performed' >&2; exit 1; }
image=$T/openwrt.ext4.new
[ "$(sha256sum "$image" | cut -d' ' -f1)" = "$want" ]
bytes=$(stat -c %s "$image")
[ "$bytes" -gt 0 ] && [ "$bytes" -le "$((need*512))" ] && [ "$((bytes%1048576))" = 0 ]
loop=$(desktop_free_loop)
loop_attached=0; mounted=0
cleanup() {
    rc=$?
    trap - EXIT HUP INT TERM
    if [ "$mounted" = 1 ]; then
        umount "$T/image-root" || { echo 'root still mounted; loop retained' >&2; exit 1; }
    fi
    [ "$loop_attached" = 0 ] || losetup -d "$loop" || exit 1
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
/system/bin/losetup -o "$((start*512))" -S "$((need*512))" "$loop" "$disk"
loop_attached=1
# Confirm the kernel actually honored the hard range bound before any write.
name=${loop##*/}
[ "$(cat /sys/class/block/$name/loop/offset)" = "$((start*512))" ]
[ "$(cat /sys/class/block/$name/loop/sizelimit)" = "$((need*512))" ]
[ "$(blockdev --getsize64 "$loop")" = "$((need*512))" ]
echo 'Writing verified image into unallocated space / 写入未分配空间'
dd if="$image" of="$loop" bs=1048576 conv=fsync
got=$(dd if="$loop" bs=1048576 count="$((bytes/1048576))" | sha256sum | cut -d' ' -f1)
[ "$got" = "$want" ]
repair=$P/desktop/files/boot/repair
# Explicit noninteractive flags: no failed repair may proceed to GPT commit.
"$repair/lib/ld-musl-aarch64.so.1" --library-path "$repair/lib:$repair/usr/lib" "$repair/usr/sbin/e2fsck" -pf "$loop" || {
    rc=$?; [ "$rc" = 1 ] || exit "$rc";
}
if [ "${GROW_FS:-1}" = 1 ]; then
"$repair/lib/ld-musl-aarch64.so.1" --library-path "$repair/lib:$repair/usr/lib" "$repair/usr/sbin/resize2fs" -f "$loop" "$((need/8))"
"$repair/lib/ld-musl-aarch64.so.1" --library-path "$repair/lib:$repair/usr/lib" "$repair/usr/sbin/e2fsck" -fn "$loop"
low=$(od -An -tu4 -j1028 -N4 "$loop" | tr -d ' \n');high=$(od -An -tu4 -j1360 -N4 "$loop" | tr -d ' \n')
[ "$high" = 0 ] && [ "$low" = "$((need/8))" ]
fi
mount -t ext4 -o ro,noload "$loop" "$T/image-root"
mounted=1
(cd "$T/image-root" && sha256sum -c "$T/image.sha256" >/dev/null)
umount "$T/image-root";mounted=0
losetup -d "$loop";loop_attached=0
trap - EXIT HUP INT TERM
check_gpt before || { echo 'GPT changed; verified image left unallocated, boot untouched' >&2; exit 1; }
write_gpt() {
    # Backup first, each write flushed; preserve all existing entries and MBR.
    dd if="$P/gpt-$1-last.bin" of="$disk" bs=512 seek="$tail" conv=notrunc,fsync &&
        dd if="$P/gpt-$1-first.bin" of="$disk" bs=512 conv=notrunc,fsync && check_gpt "$1"
}
if ! write_gpt new; then
    echo 'GPT commit failed; restoring original table, boot unchanged' >&2
    write_gpt before || echo 'GPT RESTORE FAILED: use the saved computer backup before rebooting' >&2
    exit 1
fi
rm -f "$image"
echo FREE-ROOT-VERIFIED
