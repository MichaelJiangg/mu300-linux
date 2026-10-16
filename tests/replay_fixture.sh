#!/bin/sh
# OpenWrt/BusyBox regression. All paths, AT, UCI and ifup are isolated; this
# does not restart any service or send commands to the device's real modem.
set -eu
LIB=$1
export REPLAY_FIXTURE=$(mktemp -d /tmp/mu300-replay-test.XXXXXX)
mkdir "$REPLAY_FIXTURE/state" "$REPLAY_FIXTURE/modem" "$REPLAY_FIXTURE/bin"
printf '#!/bin/sh\ncase "$3" in unisoc_modem.main.state_dir) echo "$REPLAY_FIXTURE/state";; esac\n' > "$REPLAY_FIXTURE/bin/uci"
printf '#!/bin/sh\necho ifup >> "$REPLAY_FIXTURE/commands"\n' > "$REPLAY_FIXTURE/bin/ifup"
chmod 755 "$REPLAY_FIXTURE/bin/uci" "$REPLAY_FIXTURE/bin/ifup"
export PATH="$REPLAY_FIXTURE/bin:$PATH"
export MU300_AT="$LIB/replay_fake_at.sh" UNISOC_AT_BIN="$LIB/replay_fake_at.sh"
export UNISOC_LOCK_BIN="$LIB/lock"
export MU300_DASH_DIR="$REPLAY_FIXTURE/run"
export UNISOC_APPLY_DIR="$REPLAY_FIXTURE/apply"
export UNISOC_REPLAY_MARKER="$REPLAY_FIXTURE/done"
export UNISOC_EARLY_PENDING="$REPLAY_FIXTURE/pending"
reset_modem() {
    printf '134,128,1,0,0,0' > "$REPLAY_FIXTURE/modem/tm"
    printf 1 > "$REPLAY_FIXTURE/modem/gran"
    printf 1 > "$REPLAY_FIXTURE/modem/endc"
    printf 1 > "$REPLAY_FIXTURE/modem/cfun"
    printf '0,0,0,0,0' > "$REPLAY_FIXTURE/modem/lte"
    printf '0,0,0,0' > "$REPLAY_FIXTURE/modem/nr"
    printf '12,3,1650,10' > "$REPLAY_FIXTURE/modem/cell12"
    printf '16,3' > "$REPLAY_FIXTURE/modem/cell16"
    printf '' > "$REPLAY_FIXTURE/commands"
    rm -f "$UNISOC_REPLAY_MARKER"
}
reset_modem
# No saved state and disabled auto-apply do not probe AT.
"$LIB/boot-replay"
[ ! -s "$REPLAY_FIXTURE/commands" ]
printf off > "$REPLAY_FIXTURE/state/auto_apply"
printf nsa > "$REPLAY_FIXTURE/state/mode"
"$LIB/boot-replay"
[ ! -s "$REPLAY_FIXTURE/commands" ]
printf on > "$REPLAY_FIXTURE/state/auto_apply"
printf off > "$REPLAY_FIXTURE/state/endc"
printf '3,1,3' > "$REPLAY_FIXTURE/state/lte"
printf '78,41,78' > "$REPLAY_FIXTURE/state/nr"
printf 'nr:627264,393' > "$REPLAY_FIXTURE/state/cell"
"$LIB/lock" replay early
[ -f "$UNISOC_REPLAY_MARKER" ]
[ "$(cat "$REPLAY_FIXTURE/modem/tm")" = '131,128,1' ]
[ "$(cat "$REPLAY_FIXTURE/modem/endc")" = 0 ]
[ "$(cat "$REPLAY_FIXTURE/modem/lte")" = '0,0,0,5,0' ]
[ "$(cat "$REPLAY_FIXTURE/modem/nr")" = '0,0,272,0' ]
[ "$(cat "$REPLAY_FIXTURE/modem/cell16")" = '16,3,627264,393' ]
! grep -q SFUN "$REPLAY_FIXTURE/commands"
before=$(wc -l < "$REPLAY_FIXTURE/commands")
"$LIB/boot-replay"
"$LIB/lock" replay late
[ "$(wc -l < "$REPLAY_FIXTURE/commands")" = "$before" ]
for fault in reject ignore silent restart; do
    reset_modem
    if REPLAY_TEST_FAULT=$fault "$LIB/lock" replay late; then
        echo "unexpected replay success: $fault" >&2; exit 1
    fi
    [ ! -e "$UNISOC_REPLAY_MARKER" ]
    case $fault in reject|ignore|silent) ! grep -q SFUN "$REPLAY_FIXTURE/commands" ;; esac
done
# A modem may change band masks during activation without rejecting them.
reset_modem
REPLAY_TEST_FAULT=drift "$LIB/lock" replay late
[ -e "$UNISOC_REPLAY_MARKER" ]
[ "$(cat "$REPLAY_FIXTURE/modem/lte")" = '0,0,0,0,0' ]

# Empty cell unlock by itself must trigger the generic fallback.
rm "$REPLAY_FIXTURE/state/mode" "$REPLAY_FIXTURE/state/endc" "$REPLAY_FIXTURE/state/lte" "$REPLAY_FIXTURE/state/nr"
printf '' > "$REPLAY_FIXTURE/state/cell"
reset_modem
"$LIB/boot-replay"
[ -f "$UNISOC_REPLAY_MARKER" ]
[ "$(cat "$REPLAY_FIXTURE/modem/cell12")" = '12,3' ]
[ "$(cat "$REPLAY_FIXTURE/modem/cell16")" = '16,3' ]
[ "$(grep -c 'AT+SFUN=5' "$REPLAY_FIXTURE/commands")" -eq 1 ]
printf 'REPLAY_FIXTURE_OK %s\n' "$REPLAY_FIXTURE"
