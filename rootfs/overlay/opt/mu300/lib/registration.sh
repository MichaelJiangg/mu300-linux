#!/bin/sh
# Passive cache of PS registration already received by the existing AT owner.
# No tty opens, AT commands, SIM identity, cell location or persistent writes.

mu300_registration_save() {
    local slot=$1 line=$2 kind=${3:-urc} body stat rat a b c d e rest
    local root=${MU300_REGISTRATION_DIR:-/run/mu300-registration} old= value tmp
    case "$slot" in 0|1) ;; *) return 0 ;; esac
    case "$line" in +CEREG:*) body=${line#*:} ;; *) return 0 ;; esac
    IFS=, read -r a b c d e rest <<EOF
$body
EOF
    if [ "$kind" = query ]; then stat=$b; rat=$e; else stat=$a; rat=$d; fi
    stat=${stat#"${stat%%[![:space:]]*}"}
    stat=${stat%"${stat##*[![:space:]]}"}
    rat=${rat#"${rat%%[![:space:]]*}"}
    rat=${rat%"${rat##*[![:space:]]}"}
    # Only the numeric fields are exported; never export the raw URC.
    case "$stat" in 0|1|2|3|4|5|6|7|8|9|10) ;; *) return 0 ;; esac
    case "$rat" in 0|[1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;; *) rat=null ;; esac
    value="{\"slot\":$slot,\"stat\":$stat,\"rat\":$rat}"
    [ ! -f "$root/slot$slot.json" ] || IFS= read -r old < "$root/slot$slot.json" || true
    [ "$value" != "$old" ] || return 0
    mkdir -p "$root" || return 0
    # The URC owner is the only writer for its physical group; the selected
    # dialer's scoped query may also provide a newer state atomically.
    tmp="$root/.slot$slot.$$"
    (umask 077; printf '%s\n' "$value" > "$tmp") &&
        mv -f "$tmp" "$root/slot$slot.json" || { rm -f "$tmp"; return 0; }
    # A slow or absent ubus cannot stall an AT drainer. Only state/RAT
    # transitions fork this bounded notifier, not repeated signal/cell URCs.
    ( ubus -t 1 send mu300.registration "{\"slot\":$slot}" ) \
        3<&- 4<&- </dev/null >/dev/null 2>&1 &
    return 0
}

mu300_registration_reply() {
    local slot=$1 reply=$2 line
    while IFS= read -r line; do
        case "$line" in +CEREG:*) mu300_registration_save "$slot" "$line" query ;; esac
    done <<EOF
$reply
EOF
}
