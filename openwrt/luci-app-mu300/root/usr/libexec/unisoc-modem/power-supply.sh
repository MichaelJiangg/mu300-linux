# Shared power-supply discovery. Reading never changes calibration or charging.
power_supply_read() {
    local value=
    [ -r "$1" ] || return 0
    IFS= read -r value < "$1" || :
    printf '%s\n' "$value"
}
power_battery_valid() {
    local path=$1 capacity present
    [ -d "$path" ] || return 1
    present=$(power_supply_read "$path/present")
    [ "$present" != 0 ] || return 1
    capacity=$(power_supply_read "$path/capacity")
    case "$capacity" in ''|*[!0-9]*) return 1 ;; esac
    [ "$capacity" -le 100 ] || return 1
}
power_battery_dir() {
    local root=${MU300_POWER_SUPPLY_DIR:-/sys/class/power_supply} board path
    # Preserve an explicit adapter/test override, including an unavailable one.
    if [ -n "${1:-}" ]; then
        power_battery_valid "$1" || return 1
        printf '%s\n' "$1"; return 0
    fi
    board=${MU300_POWER_DEVICE:-$(mu300-device 2>/dev/null || true)}
    # These battery-less boards expose the same FGU with synthetic readings.
    case "$board" in f50|v50) return 1 ;; esac
    for path in "$root/battery" "$root/sc27xx-fgu" "$root"/*; do
        power_battery_valid "$path" || continue
        case "${path##*/}" in battery|sc27xx-fgu) ;; *) [ "$(power_supply_read "$path/type")" = Battery ] || continue ;; esac
        printf '%s\n' "$path"; return 0
    done
    return 1
}
