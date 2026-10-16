#!/system/bin/sh
# Boot Linux from the slot opposite the currently running Android system.
#
#   mu300-linux            arm the one-shot trial and reboot
#   mu300-linux status     show what is on each slot, change nothing
#   mu300-linux --dry-run  do everything except writing and rebooting
#   mu300-linux --no-reboot arm the trial without rebooting (for installers)
#
# The switch (not the explicit bootchain sync subcommand) only writes the 32-byte AOSP bootloader_control block at offset 0x800 of the misc partition:
# the Linux slot gets the highest priority with tries_remaining = 2, Android stays bootable and marked successful. LK then
# boots Linux once. Linux writes the Android slot block back as one of its first steps, so the reboot after that
# returns to Android, and a Linux that does not boot falls back to Android by itself.
#
# bootchain sync additionally backs up and copies the Linux slot's uboot, sml,
# teecfg, trustos and vbmeta from Android. Android's slot, GPT and userdata stay intact.
BC_OFFSET=2048          # 0x800
MAGIC=42434142          # "BCAB", little endian in the struct
ANDROID_ARMED=158       # 0x9e: priority 14, tries 1, successful 1
LINUX_ARMED=47          # 0x2f: priority 15, tries 2, successful 0

DRY=0
DO_REBOOT=1
case ${1:-} in
    status) ACTION=status ;;
    --dry-run|-n) DRY=1; ACTION=switch ;;
    --no-reboot) DO_REBOOT=0; ACTION=switch ;;
    ''|switch) ACTION=switch ;;
    bootchain)
        case ${2:-check} in
            check|status) exec sh "${0%/*}/bootchain.sh" check ;;
            sync) exec sh "${0%/*}/bootchain.sh" sync ${3:+"$3"} ;;
            *) echo "usage: mu300-linux bootchain [sync]" >&2; exit 2 ;;
        esac ;;
    -h|--help|help) sed -n '2,12s/^# \{0,1\}//p' "$0"; exit 0 ;;
    *) echo "usage: mu300-linux [status|--dry-run|--no-reboot|bootchain [sync]]" >&2; exit 2 ;;
esac

die() { echo "mu300-linux: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root (su -c mu300-linux)"

# busybox: Magisk's own copy is the one that is always there, and it has the awk this script needs
for b in "${MU300_BUSYBOX:-}" "$MAGISKTMP/busybox" /data/adb/magisk/busybox /data/adb/busybox; do
    [ -x "$b" ] && { BB=$b; break; }
done
[ -n "${BB:-}" ] || die "Magisk's busybox was not found"
AWK="$BB awk"

by_name=${MU300_BY_NAME:-/dev/block/by-name}
[ -e "$by_name/misc" ] || by_name=$(dirname "$(ls -d /dev/block/platform/*/by-name/misc 2>/dev/null | head -n1)" 2>/dev/null)
MISC=$by_name/misc
BOOT_A=$by_name/boot_a
BOOT_B=$by_name/boot_b
[ -e "$MISC" ] || die "no misc partition at $MISC"
[ -e "$BOOT_A" ] && [ -e "$BOOT_B" ] || die "both boot_a and boot_b are required at $by_name"

hex_of() {  # hex_of FILE OFFSET COUNT -> lowercase hex, no spaces (only ever used for a few bytes)
    dd if="$1" bs=1 skip="$2" count="$3" 2>/dev/null | od -An -tx1 -v | tr -d ' \n'
}
head_md5() {  # head_md5 FILE -> md5 of the first 64 KiB, read in whole blocks (od on this device is very slow)
    dd if="$1" bs=4096 count=16 2>/dev/null | $BB md5sum | cut -d' ' -f1
}

live=$(hex_of "$MISC" "$BC_OFFSET" 32)
[ ${#live} -eq 64 ] || die "could not read the bootloader_control block"
[ "$(echo "$live" | cut -c9-16)" = "$MAGIC" ] || die "misc does not hold an AOSP bootloader_control block ($live)"

slot=${MU300_SLOT_SUFFIX:-$(getprop ro.boot.slot_suffix)}
case $slot in
    _a) android_boot=$BOOT_A; linux_boot=$BOOT_B; linux_slot=b; a_arm=$ANDROID_ARMED; b_arm=$LINUX_ARMED ;;
    _b) android_boot=$BOOT_B; linux_boot=$BOOT_A; linux_slot=a; a_arm=$LINUX_ARMED; b_arm=$ANDROID_ARMED ;;
    *) die "Android boot slot '$slot' is unknown" ;;
esac
a_meta=$(echo "$live" | cut -c25-26)
b_meta=$(echo "$live" | cut -c29-30)

# A boot image starts with "ANDROID!" even when it carries Linux. Reject an
# opposite slot that is still an identical copy of Android before arming it.
head_target=$(hex_of "$linux_boot" 0 8)
same=no
[ "$(head_md5 "$android_boot")" = "$(head_md5 "$linux_boot")" ] && same=yes

if [ "$ACTION" = status ]; then
    echo "running slot   ${slot:-unknown}"
    echo "slot a         priority $((0x$a_meta & 15)), tries $(( (0x$a_meta >> 4) & 7 )), successful $(( (0x$a_meta >> 7) & 1 ))"
    echo "slot b         priority $((0x$b_meta & 15)), tries $(( (0x$b_meta >> 4) & 7 )), successful $(( (0x$b_meta >> 7) & 1 ))"
    if [ "$head_target" = "414e44524f494421" ]; then
        [ "$same" = yes ] && echo "boot_$linux_slot         identical to Android's boot image (no Linux installed)" \
                          || echo "boot_$linux_slot         a boot image distinct from Android's"
    else
        echo "boot_$linux_slot         does not start with ANDROID! - not a boot image"
    fi
    exit 0
fi

[ "$head_target" = "414e44524f494421" ] || die "boot_$linux_slot is not a boot image - install Linux first"
[ "$same" = no ] || die "boot_$linux_slot is the same image as Android's boot partition: no Linux is installed"

# the new block: same as the live one, but with the slot suffix and the two metadata bytes of an armed trial,
# and a fresh CRC32 (zlib, over the first 28 bytes, stored little endian at offset 28)
new=$($AWK -v live="$live" -v am="$a_arm" -v bm="$b_arm" -v suffix="_$linux_slot" '
function xor32(a, b,   i, r, p, x, y) {
    r = 0; p = 1
    for (i = 0; i < 32; i++) {
        x = a % 2; y = b % 2; a = int(a / 2); b = int(b / 2)
        if (x != y) r += p
        p *= 2
    }
    return r
}
function h2i(s,   i, v) {   # busybox awk has no strtonum
    v = 0
    for (i = 1; i <= length(s); i++) v = v * 16 + index("0123456789abcdef", tolower(substr(s, i, 1))) - 1
    return v
}
function crc32(bytes, n,   c, i, k) {
    c = 4294967295
    for (i = 1; i <= n; i++) {
        c = xor32(c, bytes[i])
        for (k = 0; k < 8; k++) c = (c % 2) ? xor32(int(c / 2), 3988292384) : int(c / 2)
    }
    return xor32(c, 4294967295)
}
BEGIN {
    for (i = 0; i < 32; i++) b[i + 1] = h2i(substr(live, i * 2 + 1, 2))
    b[2] = (suffix == "_a" ? 97 : 98)
    b[13] = am           # slot a metadata
    b[15] = bm           # slot b metadata
    c = crc32(b, 28)
    for (i = 0; i < 4; i++) { b[29 + i] = c % 256; c = int(c / 256) }
    out = ""
    for (i = 1; i <= 32; i++) out = out sprintf("%02x", b[i])
    print out
}')
[ ${#new} -eq 64 ] || die "could not build the new bootloader_control block (awk gave '$new')"

echo "misc  now: $live"
echo "misc  new: $new"
if [ "$DRY" = 1 ]; then
    echo "dry run: nothing was written"
    exit 0
fi

tmp=${TMPDIR:-/data/local/tmp}/mu300-bc.bin
$BB printf "$(echo "$new" | sed 's/../\\x&/g')" > "$tmp" || die "could not build the block file"
[ "$($BB stat -c %s "$tmp")" = 32 ] || { rm -f "$tmp"; die "the block file is not 32 bytes"; }

$BB dd if="$tmp" of="$MISC" bs=1 seek="$BC_OFFSET" conv=notrunc,fsync 2>/dev/null || { rm -f "$tmp"; die "writing misc failed"; }
rm -f "$tmp"

back=$(hex_of "$MISC" "$BC_OFFSET" 32)
[ "$back" = "$new" ] || die "misc verify failed ($back) - reboot normally, Android is unaffected"

echo
if [ "${MU300_INSTALL_LANG:-en}" = zh ]; then
    echo "已设置下次从 $linux_slot 槽位启动一次。"
    echo "若 Linux 启动失败，设备会自动返回 Android。"
else
    echo "slot $linux_slot armed for one boot."
    echo "If it does not boot, the device returns to Android by itself."
fi
[ "$DO_REBOOT" = 0 ] && exit 0
echo "Rebooting into Linux."
sleep 3
reboot
