#!/system/bin/sh
# Write a checked image to an EXISTING independent MU300 root only.
set -eu
set -o pipefail
P=${MU300_PAYLOAD_DIR:?};T=${MU300_INSTALL_TMP:?}
. "$P/desktop-settings.env"
. "$P/ext4-geometry.sh"
dev=${1:?root device}; expected_cid=${2:?cid}; expected_sectors=${3:?size}; expected_sha=${4:?image checksum}
node=${dev##*/};disk=${node%p*}
case "$node" in mmcblk[0-9]p[0-9]*) ;; *) exit 1 ;; esac
grep -qx PARTNAME=mu300root "/sys/class/block/$node/uevent"
[ "$(cat /sys/class/block/$disk/device/cid)" = "$expected_cid" ]
[ "$(cat /sys/class/block/$node/size)" = "$expected_sectors" ]
[ -z "$(ls -A /sys/class/block/$node/holders)" ]
identity=$(cat /sys/class/block/$node/dev)
for m in /proc/[0-9]*/mountinfo; do
    [ -r "$m" ] || continue
    awk -v n="$identity" '$3==n {yes=1} END {exit !yes}' "$m" && { echo 'root partition is mounted'; exit 1; }
done
image=$T/openwrt.ext4.new
[ "$(sha256sum "$image" | cut -d' ' -f1)" = "$expected_sha" ]
size=$(stat -c %s "$image")
[ "$size" -gt 0 ] && [ "$size" -le "$((expected_sectors*512))" ]
dd if="$image" of="$dev" bs=1048576 conv=fsync
[ "$((size % 1048576))" = 0 ]
# Bounded dd exits normally; pipefail catches a short/error read without a
# second 2 GiB staging file on Android data.
actual=$(dd if="$dev" bs=1048576 count="$((size / 1048576))" | sha256sum | cut -d' ' -f1)
[ "$actual" = "$expected_sha" ]
repair=$P/desktop/files/boot/repair
"$repair/lib/ld-musl-aarch64.so.1" --library-path "$repair/lib:$repair/usr/lib" "$repair/usr/sbin/e2fsck" -pf "$dev" || {
    rc=$?; [ "$rc" = 1 ] || exit "$rc";
}
if [ "${GROW_FS:-1}" = 1 ]; then
"$repair/lib/ld-musl-aarch64.so.1" --library-path "$repair/lib:$repair/usr/lib" "$repair/usr/sbin/resize2fs" -f "$dev" "$((expected_sectors/8))"
fi
"$repair/lib/ld-musl-aarch64.so.1" --library-path "$repair/lib:$repair/usr/lib" "$repair/usr/sbin/e2fsck" -fn "$dev"
if [ "${GROW_FS:-1}" = 1 ]; then
    ext4_verify_grown "$dev" "$expected_sectors" || { echo 'root filesystem geometry does not fill target' >&2; exit 1; }
fi
mount -t ext4 -o ro,noload "$dev" "$T/image-root"
trap 'umount "$T/image-root" 2>/dev/null || :' EXIT
(cd "$T/image-root" && sha256sum -c "$T/image.sha256" >/dev/null)
umount "$T/image-root"
trap - EXIT
rm -f "$image"
echo ROOT-VERIFIED
