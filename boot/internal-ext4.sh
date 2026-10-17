# A known-bad internal filesystem must be repaired OFFLINE, before switch_root.
# Clean filesystems only read the two-byte state field; no full boot-time scan.
desktop_ext4_check() {
    local state magic rc
    magic=$(od -An -tx2 -j1080 -N2 "$1" | tr -d ' \n') || return 1
    [ "$magic" = ef53 ] || return 1
    state=$(od -An -tu2 -j1082 -N2 "$1" | tr -d ' \n') || return 1
    case $state in ''|*[!0-9]*) return 1 ;; esac
    [ "$((state & 2))" != 0 ] || [ -e /etc/mu300-desktop-fsck-force ] || return 0
    # Keep the recovery console reachable during a slow/failing offline check.
    # Healthy boots still load the saved USB mode before binding the gadget.
    if [ "${DESKTOP_USB_READY:-}" != 1 ]; then
        setup_usb_gadget
        DESKTOP_USB_READY=1
    fi
    log "stage=desktop-root-fsck dev=$1"
    /repair/lib/ld-musl-aarch64.so.1 --library-path /repair/lib:/repair/usr/lib \
        /repair/usr/sbin/e2fsck -fy "$1" > /run/mu300-root-fsck.log 2>&1
    rc=$?
    [ "$rc" -le 2 ] || { log "stage=desktop-root-fsck-failed rc=$rc"; return 1; }
    log "stage=desktop-root-fsck-done rc=$rc"
}
