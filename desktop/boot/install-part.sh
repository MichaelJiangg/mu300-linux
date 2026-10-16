# The internal-partition install (flash.py --part), finished from the
# initramfs because this is the only place userdata is unmounted: the vendor
# F2FS is shrunk with raw tools only (docs/FINDINGS.md 48), the partition
# table is changed with mu300-gpt, the image written into the new partition, and
    # the boot then restarts once into the new system (a partition created in
# this boot has no kernel node yet, so it cannot be started in this boot).
#
# Order is the safety property: the filesystem shrinks BEFORE the partition
# table changes, so any failure leaves a disk that Android can still mount
# (a partition larger than its filesystem is normal for Android).  A failed
# run keeps /data/mu300linux/part-install.conf, and the next boot retries; the
# steps check their own outcome before continuing.
#
# Sourced by boot/init; install_part_pending DEV is called once per boot with
# userdata's device.  Logs through the caller's log().
# A bounded answer declines the optional host-directory orphan dump. -f
# already enables filesystem fixes; -y alone does not suppress this prompt.
# Never inherit the console or feed unlimited answers to a metadata checker.
part_fsck() {
    local dev=$1 output=$2 worker rc
    printf "n\n" > /run/part-fsck.stdin || return 8
    /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib \
        /repair/sbin/fsck.f2fs -f "$dev" < /run/part-fsck.stdin >"$output" 2>&1 &
    worker=$!
    printf "%s %s\n" "$worker" "$output" > /run/part-check
    wait "$worker"; rc=$?
    rm -f /run/part-check /run/part-fsck.stdin
    return "$rc"
}

install_part_pending() {
    . /etc/part-progress.sh
    local dev=$1 node=${1##*/} disk=${1%p*}
    local mp=/part-install img dft lo rc cur target need low hi pstart pend found out ptarget raw want got datafs dataopts shift
    [ -b "$dev" ] || { part_fail 'userdata missing'; return 1; }
    # The request: sizes chosen by flash.py on the Android side.
    mkdir -p "$mp"
    datafs=f2fs dataopts=ro,norecovery
    if [ "$(od -An -tx2 -j 1080 -N 2 "$dev" | tr -d ' \n')" = ef53 ]; then
        datafs=ext4 dataopts=ro,noload
    fi
    mount -t "$datafs" -o "$dataopts" "$dev" "$mp" 2>/dev/null || { part_fail 'cannot mount plaintext userdata'; return 1; }
    [ -f "$mp/mu300linux/part-install.conf" ] || { umount "$mp"; part_stop; return 0; }
    PART_MIB= DATA_MIB= GROW_FS= FORMAT_DATA=0
    for kv in $(cat "$mp/mu300linux/part-install.conf"); do
        case "$kv" in
            PART_MIB=*) PART_MIB=${kv#*=} ;;
            DATA_MIB=*) DATA_MIB=${kv#*=} ;;
            GROW_FS=*) GROW_FS=${kv#*=} ;;
            FORMAT_DATA=*) FORMAT_DATA=${kv#*=} ;;
        esac
    done
    part_progress_start
    echo "1/6 checking staged image and firmware" > /run/part-status
    # Validate the staged payload before shrinking or changing GPT. A damaged
    # archive must not leave a newly carved but unusable root partition.
    img="$mp/mu300linux/part-install.img.gz" dft="$mp/mu300linux/device-files.tar"
    if [ ! -s "$img" ] || [ ! -s "$dft" ] ||
       ! gzip -t "$img" || ! tar -tf "$dft" >/dev/null; then
        umount "$mp"; part_fail 'missing or corrupt installation payload'; return 1
    fi
    raw=$(set -o pipefail; gzip -dc "$img" | wc -c) || {
        umount "$mp"; part_fail 'cannot read installation image'; return 1;
    }
    case "$GROW_FS" in 1) ;; *) GROW_FS=0 ;; esac
    umount "$mp"
    [ "$FORMAT_DATA" = 0 ] || { part_fail 'format request requires two-stage installer'; return 1; }
    case "${PART_MIB:-}" in ''|*[!0-9]*) part_fail 'bad partition size'; return 1 ;; esac
    case "${DATA_MIB:-}" in ''|*[!0-9]*) part_fail 'bad userdata size'; return 1 ;; esac
    [ "$PART_MIB" -ge 2048 ] && [ "$DATA_MIB" -ge 2048 ] ||
        { part_fail 'invalid partition/userdata sizes'; return 1; }
    target=$((DATA_MIB * 2048)) need=$((PART_MIB * 2048))
    [ "$raw" -gt 0 ] && [ "$raw" -le "$((need * 512))" ] || {
        part_fail 'image exceeds partition'; return 1;
    }
    log "stage=part-install start data=$((DATA_MIB >> 10))G part=$((PART_MIB >> 10))G"
    # Validate BOTH GPT copies and all planned geometry before moving filesystem
    # blocks. A full GPT or impossible allocation must leave userdata untouched.
    list=$(/usr/bin/ucode /usr/share/mu300-gpt list "$disk") || { part_fail 'GPT validation'; return 1; }
    found=$(echo "$list" | awk '$4 == "mu300root" {print $1}')
    if [ -z "$found" ]; then
        /usr/bin/ucode /usr/share/mu300-gpt plan "$disk" "resize:userdata:$target" "mu300root:$need" >/run/part-plan || { part_fail 'GPT allocation plan'; return 1; }
    fi

    # Two-second progress survives fractional /proc/uptime and long operations.
    # Everything on the console is plain ASCII: the framebuffer console font
    # has no CJK.  (The backlight is not touched here.)
    echo "1/6 checking userdata" > /run/part-status

    # Preserve plaintext ext4 and F2FS; the raw filesystem is never mounted
    # during shrink. Encrypted data uses the separate recovery preparation.
    if [ "$datafs" = ext4 ]; then
        awk -v n="$(cat /sys/class/block/$node/dev)" '$3 == n { found = 1 } END { exit !found }' /proc/self/mountinfo && {
            part_fail 'userdata still mounted'; return 1;
        }
        echo '2/6 checking and shrinking ext4 userdata' > /run/part-status
        /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib:/repair/usr/lib /repair/usr/sbin/e2fsck -pf "$dev" >/run/part-fsck.log 2>&1
        rc=$?; case "$rc" in 0|1) ;; *) part_fail 'ext4 fsck'; return 1 ;; esac
        shift=$(od -An -tu4 -j 1048 -N 4 "$dev" | tr -d ' \n')
        case "$shift" in 0|1|2|3|4) ;; *) part_fail 'ext4 block size'; return 1 ;; esac
        /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib:/repair/usr/lib /repair/usr/sbin/resize2fs -f "$dev" "$((target * 512 / (1024 << shift)))" >/run/part-resize.log 2>&1 || {
            part_fail 'ext4 shrink'; return 1;
        }
        /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib:/repair/usr/lib /repair/usr/sbin/e2fsck -pf "$dev" >/run/part-shrink-check.log 2>&1
        rc=$?; case "$rc" in 0|1) ;; *) part_fail 'ext4 post-shrink fsck'; return 1 ;; esac
        low=$(od -An -tu4 -j 1028 -N 4 "$dev" | tr -d ' \n')
        high=$(od -An -tu4 -j 1360 -N 4 "$dev" | tr -d ' \n')
        [ "$high" = 0 ] && [ "$((low * (1024 << shift) / 512))" = "$target" ] || {
            part_fail 'ext4 shrink size'; return 1;
        }
    else
    # 1. the filesystem, raw and unmounted. Its own superblock, not the
    #    tool's chatter, decides whether the shrink landed.
    [ "$(od -An -tx4 -j 1024 -N 4 "$dev" | tr -d ' \n')" = f2f52010 ] ||
        { part_fail 'userdata is not plaintext F2FS/ext4'; return 1; }
    awk -v n="$(cat /sys/class/block/$node/dev)" \
        '$3 == n { found = 1 } END { exit !found }' /proc/self/mountinfo &&
        { part_fail 'userdata still mounted'; return 1; }
    low=$(od -An -tx4 -j 1060 -N 4 "$dev" | tr -d ' \n')
    hi=$(od -An -tx4 -j 1064 -N 4 "$dev" | tr -d ' \n')
    [ "$hi" = 00000000 ] || { part_fail 'unsupported filesystem size'; return 1; }
    cur=$((0x$low * 8))
    if [ "$cur" != "$target" ]; then
        echo "2/6 shrinking userdata (fsck)" > /run/part-status
        log "stage=part-install shrink cur=$((cur / 2048))MiB target=$((target / 2048))MiB"
        blockdev --setrw "$dev" || { part_fail 'userdata read-only'; return 1; }
        part_fsck "$dev" /run/part-fsck.log
        rc=$?
        case "$rc" in 0|1) ;; *) part_fail "F2FS check failed rc=$rc"; return 1 ;; esac
        echo "2/6 shrinking userdata (moving blocks; this can take several minutes)" > /run/part-status
        /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib \
            /repair/sbin/resize.f2fs -s -t "$target" "$dev" \
            >/run/part-resize.log 2>&1 </dev/null
        rc=$?
        [ "$rc" = 0 ] || { part_fail "userdata resize failed rc=$rc (see /run/part-resize.log)"; return 1; }
        low=$(od -An -tx4 -j 1060 -N 4 "$dev" | tr -d ' \n')
        cur=$((0x$low * 8))
        [ "$cur" = "$target" ] ||
            { part_fail "F2FS shrink size mismatch: $((cur / 2048))MiB"; return 1; }
        log "stage=part-install shrunk $((target / 2048))MiB"
    fi
    # Check also when a previous attempt already changed the block count.
    # A new count alone cannot prove that all block moves/checkpoints finished.
    echo "2/6 verifying shrunk userdata" > /run/part-status
    part_fsck "$dev" /run/part-shrink-check.log
    rc=$?
    case "$rc" in 0|1) ;; *) part_fail "shrunk userdata check failed rc=$rc"; return 1 ;; esac
    low=$(od -An -tx4 -j 1060 -N 4 "$dev" | tr -d ' \n')
    hi=$(od -An -tx4 -j 1064 -N 4 "$dev" | tr -d ' \n')
    [ "$hi" = 00000000 ] && [ "$((0x$low * 8))" = "$target" ] || {
        part_fail 'shrunk userdata size verification'; return 1;
    }

    fi

    # 2. the partition table, only now.  ucode is called by its absolute path
    #    and its own output is checked: a piped `list` once hid a ucode that
    #    could not start (a missing library) behind awk's exit status.
    echo "3/6 creating the mu300root partition" > /run/part-status
    list=$(/usr/bin/ucode /usr/share/mu300-gpt list "$disk") ||
        { part_fail 'GPT list failed'; return 1; }
    found=$(echo "$list" | awk '$4 == "mu300root" { print $1 }')
    if [ -z "$found" ]; then
        /usr/bin/ucode /usr/share/mu300-gpt resize "$disk" userdata "$target" >/dev/null ||
            { part_fail 'GPT resize failed'; return 1; }
        out=$(/usr/bin/ucode /usr/share/mu300-gpt add "$disk" mu300root "$need") ||
            { part_fail 'GPT add failed'; return 1; }
        set -- $out
        pstart=$2 pend=$3
        log "stage=part-install partition $1 sectors $pstart-$pend"
    else
        set -- $(echo "$list" | awk '$4 == "mu300root" { print $1, $2, $3 }')
        pstart=$2 pend=$3
        log "stage=part-install partition exists $pstart-$pend"
    fi
    case "$pstart:$pend" in *[!0-9:]*|:*|*:) part_fail 'invalid partition geometry'; return 1 ;; esac
    [ $((pstart % 2048)) = 0 ] && [ $((pend - pstart + 1)) -ge "$need" ] || { part_fail 'unaligned or short partition'; return 1; }

    # 3. the image, through the whole disk at the partition's offset (the
    #    kernel's table for this boot predates it)
    echo "4/6 writing OpenWrt into the partition" > /run/part-status
    mount -t "$datafs" -o "$dataopts" "$dev" "$mp" || { part_fail 'payload remount failed'; return 1; }
    img="$mp/mu300linux/part-install.img.gz" dft="$mp/mu300linux/device-files.tar"
    [ -f "$img" ] || { umount "$mp"; part_fail 'staged image missing'; return 1; }
    log "stage=part-install write $((pstart / 2048))MiB"
    gzip -t "$img" || { umount "$mp"; part_fail 'corrupt image'; return 1; }
    local producer writer write_rc unpack_rc
    [ "$raw" -gt 0 ] && [ "$raw" -le "$((need * 512))" ] || { umount "$mp"; part_fail 'image exceeds partition'; return 1; }
    dd if=/dev/zero of="$disk" bs=1048576 seek=$((pstart / 2048)) count=4 conv=fsync 2>/dev/null ||
        { umount "$mp"; part_fail 'initial image write'; return 1; }
    rm -f /run/part-pipe
    mkfifo /run/part-pipe || { umount "$mp"; part_fail 'pipe'; return 1; }
    # The heartbeat's byte counter: /proc/<dd>/io where the kernel accounts it,
    # the disk's own sectors-written counter where it does not (a kernel built
    # without TASK_IO_ACCOUNTING has no /proc/<pid>/io).  part-progress.sh
    # prefers the first and falls back to the baseline recorded here; nothing
    # else writes the disk while the image is going in.
    echo "${disk##*/} $(awk '{print $7}' "/sys/block/${disk##*/}/stat" 2>/dev/null)" > /run/part-disk
    gunzip -c "$img" > /run/part-pipe & producer=$!
    dd if=/run/part-pipe of="$disk" bs=1048576 seek=$((pstart / 2048)) conv=fsync 2>/run/part-dd.err & writer=$!
    echo "$writer $raw" > /run/part-worker
    wait "$writer"; write_rc=$?
    [ "$write_rc" = 0 ] || kill "$producer" 2>/dev/null
    wait "$producer"; unpack_rc=$?
    rm -f /run/part-worker /run/part-pipe /run/part-disk
    [ "$write_rc:$unpack_rc" = 0:0 ] || { umount "$mp"; part_fail 'image write'; return 1; }
    # 4. the new MU300 container: OpenWrt and its device runtime are already in the image
    lo=$(losetup -f) && losetup -o $((pstart * 512)) "$lo" "$disk" ||
        { umount "$mp"; part_fail 'root loop failed'; return 1; }
    echo "4/6 verifying the complete written image" > /run/part-status
    # Keep pipefail local to these checks: init has other intentional short
    # reads. Read exactly raw bytes through the newly attached loop device.
    want=$(set -o pipefail; gzip -dc "$img" | sha256sum | cut -d' ' -f1) || {
        losetup -d "$lo"; umount "$mp"; part_fail 'source image checksum'; return 1;
    }
    got=$(set -o pipefail; head -c "$raw" "$lo" | sha256sum | cut -d' ' -f1) || {
        losetup -d "$lo"; umount "$mp"; part_fail 'image readback'; return 1;
    }
    [ "$got" = "$want" ] || {
        losetup -d "$lo"; umount "$mp"; part_fail 'image readback checksum mismatch'; return 1;
    }
    mkdir -p /part-root
    if [ "$GROW_FS" = 1 ]; then
        # The partition as it stands, not the size chosen on the PC: a re-run
        # reuses the existing mu300root, and the chosen number can be smaller than
        # it -- resizing to that number would shrink a system that works, and
        # the superblock check would report the shrink as a success.
        ptarget=$((pend - pstart + 1))
        echo "5/6 expanding filesystem to $((ptarget / 2048)) MiB (offline)" > /run/part-status
        part_grow_ext4 "$lo" "$ptarget" || {
            losetup -d "$lo"; umount "$mp"; part_fail 'filesystem expansion/size verification'; return 1;
        }
    else
        echo "5/6 keeping the image's filesystem size" > /run/part-status
    fi
    echo "6/6 finishing the new root" > /run/part-status
    if mount -t ext4 "$lo" /part-root; then
        if [ -f "$dft" ]; then
            tar -xf "$dft" -C /part-root || { umount /part-root; losetup -d "$lo"; umount "$mp"; part_fail 'firmware archive'; return 1; }
            sha256sum "$dft" | cut -d' ' -f1 > /part-root/openwrt/etc/mu300/device-files.stamp
            log "stage=part-install device-files"
        fi
        [ -x /part-root/openwrt/sbin/init ] && [ -s /part-root/openwrt/lib/firmware/wcnmodem.bin ] ||
            { umount /part-root; losetup -d "$lo"; umount "$mp"; part_fail 'incomplete system'; return 1; }
        mkdir -p /part-root/.mu300
        echo openwrt > /part-root/.mu300/boot-os
        echo 5 > /part-root/.mu300/boot-attempts
        echo 0 > /part-root/.mu300/boot-tries
        echo linux > /part-root/openwrt/etc/mu300/default-boot
        echo part > /part-root/openwrt/etc/mu300/desktop-mode
        sync
        umount /part-root || { part_fail 'root unmount'; return 1; }
    else
        losetup -d "$lo"; umount "$mp"; part_fail 'new root mount'; return 1
    fi
    losetup -d "$lo"
    umount "$mp"

    # The payloads are done with. Removing them is the one write the whole
    # flow makes to the vendor F2FS from Linux; a few unlinks with a clean
    # unmount, the same bargain boot/init takes for one-boot choices.
    if mount -t "$datafs" -o noatime,nodiratime "$dev" "$mp" 2>/dev/null; then
        rm -f "$mp/mu300linux/part-install.img.gz" "$mp/mu300linux/part-install.conf" \
              "$mp/mu300linux/part-install.settings" "$mp/mu300linux/device-files.tar"
        sync
        umount "$mp"
        log "stage=part-install cleaned"
    else
        log "stage=part-install clean-skipped"
    fi
    sync
    part_stop
    log "stage=part-install done"
    # A partition the install created exists in the kernel's table only from
    # the next boot (this boot read the table before it existed), so the
    # selection cannot start it now: restart once, cleanly, into it.  The
    # native MU300 boot counter protects the first start.
    # LK counts slot b's tries down as it boots it, and one try left on a slot
    # that is not successful rolls back at once (nowhere to land but Android):
    # this install boot consumed one, so refill the trial before the restart
    # -- the next boot is the system's first, and mu300-next-boot rearms it.
    write_misc_bc "$DESKTOP_LINUX_BC" part-install-rearm || { part_fail 'boot control write'; return 1; }
    cmp -s /run/bc-check.bin "$DESKTOP_LINUX_BC" || { part_fail 'boot control verification'; return 1; }
    log "stage=part-install rebooting into the new system"
    reboot -f
    return 0
}
