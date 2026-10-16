#!/bin/sh
# Run on F50 ash with a fake FIFO only. Never opens a modem or changes settings.
set -eu
client=$1
testdir=$(mktemp -d /tmp/mu300-at-client-test.XXXXXX)
export MU300_AT_DIR=$testdir MU300_AT_DEV=$testdir/never-a-modem MU300_AT_LOCK_WAIT=0
mkfifo "$testdir/cmd"
pause() { /opt/mu300/bin/busybox sleep 0.01; }
fail() { echo "FAIL: $* ($testdir)" >&2; exit 1; }
run_case() {
    expected=$1; reply=$2; command=$3
    rm -f "$testdir/ready"
    (
        exec 7<> "$testdir/cmd"
        : > "$testdir/ready"
        IFS= read -r -t 3 request <&7 || exit 1
        printf '%s\n' "$request" > "$testdir/request"
        rest=${request#* }; answer=${rest%% *}
        case $answer in "$testdir"/answer.*) ;; *) exit 1 ;; esac
        printf '%b' "$reply" > "$answer.part"
        mv "$answer.part" "$answer"
    ) &
    peer=$!
    n=0
    until [ -f "$testdir/ready" ]; do
        n=$((n+1)); [ "$n" -lt 100 ] || fail 'peer not ready'
        pause
    done
    status=0
    sh "$client" -t 2 "$command" > "$testdir/out" 2> "$testdir/err" || status=$?
    wait "$peer" || fail 'fake peer failed'
    [ "$status" = "$expected" ] || fail "expected $expected, got $status"
    IFS= read -r request < "$testdir/request"
    rest=${request#* }; actual=${rest#* }
    [ "$actual" = "$command" ] || fail 'command bytes changed'
    [ ! -d "$testdir/lock" ] || fail 'client lock leaked'
}
run_case 0 'OK\n' AT
run_case 0 '\r\n+VALUE: 1\r\nOK\r\n\r\n' AT
run_case 0 '+CMS ERROR: 302\n' AT
run_case 1 'OKAY\n' AT
run_case 1 'OK\n+VALUE: unfinished' AT
run_case 1 'OK' AT
run_case 0 'OK\n' 'AT+CSCS?;+COPS?'
sms=$(printf 'AT+CMGS=5\r001122334455\032')
run_case 0 'OK\n' "$sms"
read -r before rest < /proc/uptime
status=0
sh "$client" -t 1 AT > "$testdir/out" 2> "$testdir/err" || status=$?
read -r after rest < /proc/uptime
[ "$status" != 0 ] || fail 'missing daemon succeeded'
elapsed=$(( ${after%.*} - ${before%.*} ))
[ "$elapsed" -le 3 ] || fail 'deadline exceeded'
[ ! -d "$testdir/lock" ] || fail 'timeout lock leaked'
echo "PASS: ash FIFO boundary/SMS/elapsed deadline; isolated directory $testdir"
