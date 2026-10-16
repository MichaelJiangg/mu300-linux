#!/bin/sh
# Real OpenWrt JSON/ucode backend; private fixtures and fake HTTPS only.
set -e
source=$1
base=$(mktemp -d /tmp/forward-answer.XXXXXX)
trap 'rm -rf "$base"' EXIT
export MU300_FORWARD_DIR=$base/config MU300_FORWARD_RESULT=$base/result MU300_FORWARD_RUNTIME=$base
export MU300_SMS_POOL=$base/pool
export MU300_FORWARD_RENDERER=${source%/*}/forward-template.uc MU300_FORWARD_ANSWER=${source%/*}/forward-answer.uc
mkdir -p "$base/config"
mkdir -p "$base/pool/msg" "$base/pool/sim1/msg"
printf '0\n' > "$base/pool/next_id"
printf '0\n' > "$base/pool/sim1/next_id"
sed '/^case "${1:-}" in/,$d' "$source" > "$base/lib.sh"
set +e
. "$base/lib.sh"
set -e
fail() { echo "FAIL: $*" >&2; exit 1; }
uci() { echo 2; }
resolve_public() { RESOLVE=example.com:443:8.8.8.8; PICKED_IP=8.8.8.8; }
curl() {
    while [ "$#" -gt 0 ]; do
        if [ "$1" = -o ]; then shift; printf '%s' "$ANSWER" > "$1"; fi
        shift
    done
    printf 200
}
set_profile() {
    _r=$(printf '%s' "$1" | set_config)
    [ "$(printf '%s' "$_r" | jsonfilter -e '@.ok')" = 1 ] || fail "config $_r"
    load_config
}
# Legacy saved profiles have no success rule and must remain readable.
printf '%s' '{"enabled":1,"method":"webhook","webhook_url":"https://example.com/hook"}' > "$CONFIG"
load_config || fail 'legacy profile unreadable'
[ -z "$webhook_expect" ] || fail 'legacy rule not empty'
set_profile '{"enabled":1,"method":"webhook","webhook_url":"https://example.com/hook","template_language":"en","webhook_expect":"errcode=0"}'
get_view > "$base/view"
[ "$(jsonfilter -i "$base/view" -e '@.config.webhook_expect')" = errcode=0 ] || fail 'get rule'
set_profile '{"enabled":1,"method":"webhook","webhook_url":"https://example.com/hook","template_language":"en"}'
[ "$webhook_expect" = errcode=0 ] || fail 'older editor erased rule'
ANSWER='{"errcode":0}'; deliver test NMS '' || fail 'success rejected'
ANSWER='{"errcode":400,"message":"PRIVATE_RESPONSE"}'
if deliver test NMS ''; then fail 'HTTP 200 service refusal accepted'; fi
[ "$DELIVER_RESULT" = service_rejected ] || fail 'rejection result'
ANSWER='{"nested":{"errcode":0}}'
if deliver test NMS ''; then fail 'nested key accepted'; fi
[ "$DELIVER_RESULT" = service_answer_missing ] || fail 'missing result'
for ANSWER in '[]' 'not JSON' '{"errcode":[]}' '{"errcode":{"value":0}}' ''; do
    if deliver test NMS ''; then fail 'invalid reply accepted'; fi
done
webhook_expect=ok=true
ANSWER='{"ok":true}'; deliver test NMS '' || fail 'boolean success'
ANSWER='{"ok":false}'; if deliver test NMS ''; then fail 'boolean refusal'; fi
webhook_expect=errcode=0
ANSWER='{"errcode":"0"}'; deliver test NMS '' || fail 'string success'
ANSWER=$(printf '%4100s' ' ')
if deliver test NMS ''; then fail 'oversize body accepted'; fi
webhook_expect=
ANSWER='not JSON'; deliver test NMS '' || fail 'legacy HTTP-only behavior changed'
method=dingtalk; dingtalk_webhook='https://oapi.dingtalk.com/robot/send?access_token=TEST'; dingtalk_secret=
ANSWER='{"errcode":1}'; if deliver test NMS ''; then fail 'DingTalk regression'; fi
ANSWER='{"errcode":0}'; deliver test NMS '' || fail 'DingTalk success'
for rule in 'bad key=0' 'errcode=$(reboot)' 'errcode=0;reboot' 'x=' '=0' 'x=12345678901234567' 'x=-' 'x=--1'; do
    if answer_rule_valid "$rule"; then fail 'unsafe rule accepted'; fi
done
# Clear only the history name, never a link target, config or processing cursor.
printf 'original\n' > "$base/untouched"
ln -s "$base/untouched" "$HISTORY"
printf 'cursor\n' > "$STATE"
before=$(sha256sum "$CONFIG" "$STATE")
clear_history > "$base/clear"
[ "$(jsonfilter -i "$base/clear" -e '@.ok')" = 1 ] || fail 'clear result'
[ ! -L "$HISTORY" ] && [ "$(cat "$base/untouched")" = original ] || fail 'clear followed link'
[ "$before" = "$(sha256sum "$CONFIG" "$STATE")" ] || fail 'clear changed state'
test_gate || fail 'first test gate'
if test_gate; then fail 'rapid duplicate test allowed'; fi
printf 'PASS: rule persistence, real JSON scalar checks, private finite results, HTTP-only compatibility, DingTalk, unsafe input, clear isolation and test throttle\n'
