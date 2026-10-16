#!/bin/sh
# TF-only storage primitives. Sourced by android-install.sh and tested with
# fixture sysfs/mountinfo trees; no environment override of production paths.
tf_die() { say_i18n "TF 安装中止：$1" "TF installation stopped: $1"; return 1; }
tf_step() { "$MU300_BUSYBOX" sh "$P/tf-stage.sh" "$@"; }
tf_mounts_for_ids() {
    # mountinfo field 3 is major:minor, independent of /dev/block/vold aliases.
    awk -v ids="$1" 'BEGIN { n=split(ids,a," "); for(i=1;i<=n;i++) wanted[a[i]]=1 }
        wanted[$3] { print $1, $5 }' "$2"
}
tf_namespace_gone() {
    # An exited/zombie task can still have a proc directory, but mountinfo
    # returns EINVAL after its namespace was released. Never exempt live tasks
    # merely because a proc read failed (permissions/SELinux must fail closed).
    [ -e "$1/mountinfo" ] || return 0
    tf_process_state=$(awk '/^State:/ {print $2}' "$1/status" 2>/dev/null) || return 1
    case $tf_process_state in
        Z|X) if ! readlink "$1/ns/mnt" >/dev/null 2>&1; then return 0; fi ;;
    esac
    return 1
}
tf_release() {
    [ "$(readlink /proc/self/ns/mnt)" = "$(readlink /proc/1/ns/mnt)" ] || {
        tf_die 'run in Android init mount namespace (nsenter -t 1 -m)'; return 1;
    }
    tf_target=$(readlink -f "$1") || return 1
    case $tf_target in /dev/block/mmcblk1|/dev/block/mmcblk1p[0-9]*) ;; *) tf_die 'unexpected TF device'; return 1 ;; esac
    tf_ids=
    # Formatting a whole card requires releasing every partition. For a
    # partition install do not disturb other partitions or other removable disks.
    for tf_sys in /sys/class/block/mmcblk1 /sys/class/block/mmcblk1p*; do
        [ -r "$tf_sys/dev" ] || continue
        # The raw parent overlaps a selected partition too. An accidental
        # whole-card mount must not be overlooked just because p1 was selected.
        [ "$tf_target" = /dev/block/mmcblk1 ] || [ "${tf_sys##*/}" = mmcblk1 ] || \
            [ "${tf_sys##*/}" = "${tf_target##*/}" ] || continue
        tf_id=$(cat "$tf_sys/dev") || return 1
        for tf_holder in "$tf_sys"/holders/*; do
            [ ! -e "$tf_holder" ] || { tf_die "TF has a device-mapper/stacked holder: $tf_holder"; return 1; }
        done
        tf_ids="$tf_ids $tf_id"
    done
    [ -n "$tf_ids" ] || { tf_die 'missing TF device identity'; return 1; }
    # vold unmount is asynchronous. This is an operation deadline, not a
    # boot delay. No forced/lazy unmount and no format until every alias is gone.
    # Android reports unsupported/unreadable public filesystems (including
    # some existing Linux TF installs) as "unmountable", not "unmounted".
    # That is NOT a mounted state; still verify mountinfo below before writes.
    tf_n=0
    tf_requested=' '
    while [ "$tf_n" -lt 15 ]; do
        tf_busy=
        tf_volumes=$(sm list-volumes all) || return 1
        for tf_id in $tf_ids; do
            tf_vol=public:$(echo "$tf_id" | tr : ,)
            tf_state=$(printf '%s\n' "$tf_volumes" | awk -v v="$tf_vol" '$1==v {print $2}')
            case $tf_state in
                ''|unmounted|unmountable) ;;
                mounted|mounted_ro)
                    tf_busy=1
                    case $tf_requested in
                        *" $tf_vol "*) ;;
                        *)
                            say_i18n "正在释放 $tf_vol ($tf_state)" "releasing $tf_vol ($tf_state)"
                            sm unmount "$tf_vol" || return 1
                            tf_requested="$tf_requested$tf_vol " ;;
                    esac ;;
                checking|ejecting) tf_busy=1 ;;
                *) tf_die "unexpected vold state: $tf_vol $tf_state"; return 1 ;;
            esac
        done
        [ -n "$tf_busy" ] || break
        tf_n=$((tf_n + 1)); sleep 1
    done
    [ -z "$tf_busy" ] || {
        printf '%s\n' "$tf_volumes"
        tf_die 'vold did not release TF (see volume states above)'; return 1;
    }
    # In init's mount namespace: remove any remaining direct mounts, children
    # first. A mount remaining in another namespace is a hard refusal, not an
    # invitation to enter arbitrary app namespaces and detach their storage.
    tf_mounts_for_ids "$tf_ids" /proc/self/mountinfo | sort -rn > "$T/tf-mounts"
    while read -r tf_mid tf_path; do
        [ -n "$tf_mid" ] || continue
        tf_path=$(printf '%b' "$tf_path")
        umount "$tf_path" || return 1
    done < "$T/tf-mounts"
    for tf_info in /proc/[0-9]*/mountinfo; do
        [ -r "$tf_info" ] || continue
        tf_left=$(tf_mounts_for_ids "$tf_ids" "$tf_info" 2>/dev/null) || {
            if tf_namespace_gone "${tf_info%/mountinfo}"; then continue; fi
            tf_die "cannot inspect $tf_info"; return 1
        }
        [ -z "$tf_left" ] || { tf_die "TF still mounted ($tf_info): $tf_left"; return 1; }
    done
}
tf_read_super() {
    # Bound BEFORE I/O; check the read itself AND byte count. A short read is
    # never a blank disk. Only aligned raw-device reads (no bs=1 raw seeks).
    tf_sectors=$(blockdev --getsz "$1") || return 1
    case $tf_sectors in ''|*[!0-9]*) return 1 ;; esac
    [ "$tf_sectors" -ge 8 ] || return 1
    dd if="$1" of="$T/tf-super" bs=512 count=8 || return 1
    [ "$(wc -c < "$T/tf-super")" -eq 4096 ] || return 1
}
tf_read_requirements() {
    # Packaging may run on Windows. Accept LF/CRLF without modifying the
    # checksummed payload file; reject malformed/extra fields or records.
    tf_requirements=$(awk '
        NR == 1 {
            sub(/\r$/, "")
            if (NF != 2 || $1 !~ /^[0-9]+$/ || $2 !~ /^[0-9]+$/) exit 1
            print $1, $2
            next
        }
        { exit 1 }
        END { if (NR != 1) exit 1 }
    ' "$1") || return 1
    IFS=' ' read -r required_kib required_inodes <<EOF
$tf_requirements
EOF
    [ "$required_kib" -gt 0 ] && [ "$required_inodes" -gt 0 ]
}

tf_capacity() {
    # Arguments are sectors, required KiB and required inodes. Sector arithmetic
    # avoids Android mksh byte overflow. We run TF workers with 64-bit BusyBox ash.
    tf_capacity_error='invalid sector count or rootfs requirements'
    case $1:$2:$3 in *[!0-9:]*|:*|*::*|*:) return 1 ;; esac
    [ "$1" -gt 0 ] && [ "$2" -gt 0 ] && [ "$3" -gt 0 ] || return 1
    tf_capacity_error="target=$(( $1 / 2 )) KiB, required=$2 KiB"
    [ $(( $1 / 2 )) -ge "$2" ] || return 1
    tf_capacity_error=
}

if [ "${1:-}" = --release ]; then
    set -eu
    P=${MU300_PAYLOAD_DIR:?}; T=${MU300_INSTALL_TMP:?}
    say_i18n() { if [ "${MU300_INSTALL_LANG:-en}" = zh ]; then echo "$1"; else echo "$2"; fi; }
    tf_release "$2"
fi
