#!/bin/sh
# A minimal shell client of the MU300 voice API (docs/voice-api.md): print every call event, and with --answer
# answer each incoming call.
#   voice-events.sh [--answer]
# Run it as root, or as a member of mu300voice (--answer then goes through sudo: contrib/voice-api/sudoers.mu300voice).
# It reads the event socket when socat or an nc with -U is there, and "mu300-voice events" (the same lines, from the
# feed file) when not. Each line is one JSON object; the fields read below are flat, so sed is enough here - a real
# client should use a JSON parser.
set -u
VOICE=/opt/mu300/bin/mu300-voice
SOCK=/run/mu300-voice/events.sock
answer=0; [ "${1:-}" = --answer ] && answer=1

field() {   # field NAME LINE -> the value of a string or number field, quotes removed ("" for null or absent)
    printf '%s\n' "$2" | sed -n "s/.*\"$1\":\"\{0,1\}\([^\",}]*\)\"\{0,1\}[,}].*/\1/p" | sed 's/^null$//'
}
mask() { sed 's/\(+[0-9][0-9]\)[0-9]*\([0-9][0-9]\)/\1********\2/g'; }

stream() {
    if [ -S "$SOCK" ] && command -v socat >/dev/null 2>&1; then exec socat -u "UNIX-CONNECT:$SOCK" -
    elif [ -S "$SOCK" ] && nc -h 2>&1 | grep -q -- '-U'; then exec nc -U "$SOCK"
    else exec "$VOICE" events; fi
}

stream | while IFS= read -r line; do
    ev=$(field event "$line")
    case $ev in
        call)
            id=$(field id "$line"); state=$(field state "$line"); prev=$(field prev "$line")
            number=$(field number "$line")
            echo "call $id ($(field dir "$line")): $prev -> $state ${number:-hidden}" | mask
            if [ "$answer" = 1 ] && [ "$state" = incoming ] && [ "$prev" = none ]; then
                if [ "$(id -u)" = 0 ]; then "$VOICE" answer "$id" --json
                else sudo -n "$VOICE" answer "$id" --json; fi
            fi ;;
        audio) echo "audio $(field state "$line"): playback $(field playback "$line"), capture $(field capture "$line")" ;;
        snapshot) echo "now: $line" | mask ;;
    esac
done
