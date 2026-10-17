# Desktop-only storage policy; this file is never added to the Magisk boot.
desktop_part() {
    local match= u
    for u in /sys/class/block/mmcblk*p*/uevent; do
        grep -qx "PARTNAME=$1" "$u" 2>/dev/null || continue
        [ -z "$match" ] || return 1
        match=/dev/$(basename "$(dirname "$u")")
    done
    [ -n "$match" ] && echo "$match"
}
desktop_storage_start() {
    DESKTOP_MODE=$(cat /etc/mu300-desktop-root-mode)
    DESKTOP_LINUX_BC=/etc/misc-bc-slot-b-trial.bin
    [ "$linux_slot" != a ] || DESKTOP_LINUX_BC=/etc/misc-bc-slot-a-trial.bin
    case "$DESKTOP_MODE" in
        prepare|install-part)
            touch /run/stay
            mkdir -p /run/mu300-desktop-www
            echo 'Starting offline installation; waiting for storage checks' > /run/mu300-desktop-www/progress.txt
            httpd -p "$NET.1:8089" -h /run/mu300-desktop-www &
            . /etc/part-progress.sh
            . /etc/part-prepare.sh
            . /etc/install-part.sh
            if [ "$DESKTOP_MODE" = prepare ]; then
                part_prepare || { part_fail 'prepare failed'; while :; do sleep 10; done; }
                restore_android; reboot -f
                while :; do sleep 10; done
            fi
            local d identity cid node start before target actual
            d=$(desktop_part userdata) || { part_fail 'userdata identity'; return 1; }
            IFS=: read -r cid node start before target < /etc/mu300-desktop-identity
            [ "$d" = "/dev/$node" ] && [ "$cid" = "$(cat /sys/class/block/${node%p*}/device/cid)" ] &&
                [ "$start" = "$(cat /sys/class/block/$node/start)" ] || { part_fail 'wrong installation device'; return 1; }
            actual=$(cat /sys/class/block/$node/size)
            [ "$actual" = "$before" ] || [ "$actual" = "$target" ] || { part_fail 'userdata geometry changed'; return 1; }
            install_part_pending "$d" || { part_fail 'install failed'; while :; do sleep 10; done; }
            DESKTOP_MODE=part ;;
    esac
}
. /etc/mu300-internal-ext4.sh

desktop_mount_root() {
    local d u magic label n datafs dev loops
    case "$DESKTOP_MODE" in
        part)
            d=$(desktop_part mu300root) || return 1
            desktop_ext4_check "$d" || return 1
            mount -t ext4 -o noatime "$d" /disk || return 1
            [ -x /disk/openwrt/sbin/init ] && [ -f /disk/.mu300/boot-os ] || { umount /disk; return 1; }
            rootloop=$d ;;
        data-image)
            d=$(desktop_part userdata) || return 1
            mkdir -p /mu300-data
            datafs=f2fs
            [ "$(od -An -tx2 -j 1080 -N2 "$d" | tr -d ' \n')" != ef53 ] || datafs=ext4
            # Missing/encrypted payloads must not mount userdata read-write.
            case "$datafs" in ext4) mount -t ext4 -o ro,noload "$d" /mu300-data ;; *) mount -t f2fs -o ro,norecovery "$d" /mu300-data ;; esac || return 1
            [ -f /mu300-data/mu300linux/openwrt.ext4 ] || { umount /mu300-data; return 1; }
            umount /mu300-data || return 1
            mount -t "$datafs" -o noatime "$d" /mu300-data || return 1
            [ -f /mu300-data/mu300linux/openwrt.ext4 ] || { umount /mu300-data; return 1; }
            loops=$(losetup -f)
            losetup "$loops" /mu300-data/mu300linux/openwrt.ext4 || return 1
            mount -t ext4 -o noatime "$loops" /disk || { losetup -d "$loops"; return 1; }
            rootloop=$loops
            # Keep the backing mount through switch_root, just like the container.
            mkdir -p /disk/openwrt/mnt/mu300-data
            mount --move /mu300-data /disk/openwrt/mnt/mu300-data ;;
        sd)
            for n in $(seq 1 8); do
                for d in /dev/mmcblk[1-9]p1 /dev/mmcblk[1-9]; do
                    [ -b "$d" ] || continue
                    dd if="$d" of=/run/sd-super bs=512 count=8 2>/dev/null || continue
                    [ "$(wc -c < /run/sd-super)" = 4096 ] || continue
                    magic=$(od -An -tx2 -j1080 -N2 /run/sd-super | tr -d ' \n')
                    label=$(dd if=/run/sd-super bs=1 skip=1144 count=16 2>/dev/null | tr -d '\000')
                    [ "$magic" = ef53 ] && [ "$label" = mu300sd ] || continue
                    mount -t ext4 -o noatime "$d" /disk || return 1
                    rootloop=$d sd_root=$d; return 0
                done
                mdev -s; sleep 1
            done
            return 1 ;;
        *) return 1 ;;
    esac
}
