#!/bin/sh
set -e
source=$1
base=$(mktemp -d /tmp/mu300-forward-events.XXXXXX)
# Extract only trusted production definitions; bypass the CLI dispatcher.
sed '/^case "${1:-}" in/,$d' "$source" > "$base/lib.sh"
export MU300_FORWARD_DIR=$base/config MU300_SMS_POOL=$base/pool MU300_FORWARD_RESULT=$base/result
export MU300_FORWARD_BATTERY=$base/no-battery
export MU300_SMS_BIN=/bin/false
mkdir -p "$base/config" "$base/pool/msg"
. "$base/lib.sh"
# Fake delivery sink: never invokes an SMTP/Webhook/SMS transport.
deliver() { printf '%s\n' "$1" >> "$base/deliveries"; DELIVER_RESULT=sent; }
enabled=1 method=smtp smtp_password=SECRET smtp_to=private@example.com
last_id=0 since=1 power_percent=-1 power_status=none power_last_result=idle
blacklist_phone= blacklist_keywords=BLOCK
printf '3\n' > "$POOL/next_id"
printf 'dir: mt\nfrom: PRIVATE\nreceived: 2\nscts: old\nsource: direct\ncoding: pdu\n\nBODY_SECRET\n' > "$POOL/msg/000001"
printf 'dir: mt\nfrom: PRIVATE\nreceived: 2\nscts: old\nsource: direct\ncoding: pdu\n\nBLOCK\n' > "$POOL/msg/000002"
printf 'dir: mt\nfrom: PRIVATE\nreceived: 2\nscts: old\nsource: sim\ncoding: pdu\n\nOLD_SIM\n' > "$POOL/msg/000003"
process_sms; process_sms; process_sms
test "$(wc -l < "$HISTORY")" = 1
test "$(wc -l < "$base/deliveries")" = 1
load_state; process_sms
test "$(wc -l < "$base/deliveries")" = 1
n=0
while [ "$n" -lt 35 ]; do record_delivery test; n=$((n+1)); done
test "$(wc -l < "$HISTORY")" = 30
json_init; add_status; json_dump > "$base/status.json"
test "$(jsonfilter -i "$base/status.json" -e '@.status.history[0].kind')" = test
if grep -qE 'SECRET|PRIVATE|example.com|OLD_SIM|BLOCK' "$base/status.json"; then exit 1; fi
# SIM 2 shares delivery settings, never SIM 1's cursor or inbox. Transport is
# still the fake function above; these tests cannot contact real recipients.
uci() { case "$*" in *unisoc_modem.main.sim_slots*) echo 2 ;; *) return 1 ;; esac; }
mkdir -p "$POOL/sim1/msg"
printf '1\n' > "$POOL/sim1/next_id"
cp "$POOL/msg/000001" "$POOL/sim1/msg/000001"
process_second_sim
test "$(wc -l < "$base/deliveries")" = 1
printf '2\n' > "$POOL/sim1/next_id"
printf 'dir: mt\nfrom: PRIVATE\nreceived: %s\nscts: old\nsource: direct\ncoding: pdu\n\nNEW_SIM2\n' "$(( $(date +%s) + 1 ))" > "$POOL/sim1/msg/000002"
process_second_sim
test "$(wc -l < "$base/deliveries")" = 2
process_second_sim
test "$(wc -l < "$base/deliveries")" = 2
test "$(cut -d'|' -f1 "$STATE")" = 3
test "$(cut -d'|' -f1 "$BASE/state.sim1")" = 2
printf '3\n' > "$POOL/sim1/next_id"
cp "$POOL/sim1/msg/000002" "$POOL/sim1/msg/000003"
reset_second_barrier; process_second_sim
test "$(wc -l < "$base/deliveries")" = 2
echo "PASS new SMS event/history cap/privacy/blacklist/restart/no old replay: $base"
