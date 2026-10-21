# Shared SMS root selection; callers scope SIM2 once after resolving the root.
# The old dashboard default was never the native receiver's pool. Treat that
# default as an alias only for the native backend; never move/delete records.
mu300_sms_pool() {
    if [ -n "${MU300_SMS_POOL:-}" ]; then
        printf '%s\n' "$MU300_SMS_POOL"
        return
    fi
    local pool command=${MU300_SMS_BIN:-}
    pool=$(uci -q get unisoc_modem.main.sms_pool 2>/dev/null) || pool=
    if [ "${1:-native}" = adapter ]; then
        [ -n "$command" ] || command=$(uci -q get unisoc_modem.main.sms_command 2>/dev/null) || command=
        case ${command##*/} in
            ''|mu300-sms) ;;
            *) printf '%s\n' "${pool:-/etc/unisoc-modem/sms}"; return ;;
        esac
    fi
    case $pool in ''|/etc/unisoc-modem/sms|/etc/unisoc-modem/sms/) pool=/etc/mu300/sms ;; esac
    printf '%s\n' "$pool"
}
