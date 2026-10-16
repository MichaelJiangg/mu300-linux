#!/bin/sh
# Real jshn/ucode integration; all destinations, inboxes and transports isolated.
set -e
source=$1
base=$(mktemp -d /tmp/mu300-forward-profiles.XXXXXX)
export MU300_FORWARD_DIR=$base/config MU300_SMS_POOL=$base/pool MU300_FORWARD_RESULT=$base/result
export MU300_FORWARD_BATTERY=$base/battery MU300_SMS_BIN=/bin/false
export MU300_FORWARD_RUNTIME=$base
export MU300_FORWARD_RENDERER=${source%/*}/forward-template.uc
export MU300_FORWARD_ANSWER=${source%/*}/forward-answer.uc
mkdir -p "$base/config" "$base/pool/msg" "$base/pool/sim1/msg"
printf '0\n' > "$base/pool/next_id"
printf '0\n' > "$base/pool/sim1/next_id"
sed '/^case "${1:-}" in/,$d' "$source" > "$base/lib.sh"
. "$base/lib.sh"
uci() { case "$*" in *unisoc_modem.main.sim_slots*) echo 2 ;; *) return 1 ;; esac; }
fail() { echo "FAIL: $*" >&2; exit 1; }
check_set() {
    reply=$(printf '%s' "$1" | set_config)
    [ "$(printf '%s' "$reply" | jsonfilter -e '@.ok')" = 1 ] || fail "set $reply"
}
expect_error() {
    reply=$(printf '%s' "$1" | set_config)
    [ "$(printf '%s' "$reply" | jsonfilter -e '@.ok')" = 0 ] || fail 'invalid config accepted'
}
check_set '{"enabled":1,"method":"webhook","webhook_url":"https://shared.example.com/hook","template_language":"en"}'
get_view shared > "$base/view"
[ "$(jsonfilter -i "$base/view" -e '@.mode')" = shared ]
[ "$(jsonfilter -i "$base/view" -e '@.config.webhook_timeout')" = 12 ]
# Shared settings survive adding independent profiles; secrets never cross profiles.
check_set '{"profile":"sim0","enabled":1,"method":"smtp","smtp_host":"smtp.example.com","smtp_username":"a@example.com","smtp_to":"b@example.com","smtp_password":"SECRET_A"}'
check_set '{"profile":"sim1","enabled":1,"method":"smtp","smtp_host":"smtp.example.com","smtp_username":"c@example.com","smtp_to":"d@example.com","smtp_password":"SECRET_B"}'
check_set '{"profile":"sim0","enabled":1,"method":"smtp","smtp_host":"smtp.example.com","smtp_username":"a@example.com","smtp_to":"b@example.com","smtp_password":""}'
[ "$(jsonfilter -i "$BASE/config.sim0.json" -e '@.smtp_password')" = SECRET_A ]
[ "$(jsonfilter -i "$BASE/config.sim1.json" -e '@.smtp_password')" = SECRET_B ]
get_view sim0 > "$base/view"
! grep -q SECRET "$base/view"
check_set '{"profile":"sim0","enabled":1,"method":"webhook","webhook_url":"https://sim0.example.com/hook","clear_smtp_password":1}'
check_set '{"profile":"sim1","enabled":1,"method":"webhook","webhook_url":"https://sim1.example.com/hook","clear_smtp_password":1}'
old_sms() {
    printf '%s\n' "$2" > "$1/next_id"
    printf 'dir: mt\nfrom: 10010\nreceived: %s\nscts: old\nsource: direct\ncoding: pdu\n\n{from} "quoted"\n' "$(date +%s)" > "$1/msg/$(printf '%06d' "$2")"
}
old_sms "$ROOT_POOL" 1; old_sms "$ROOT_POOL/sim1" 1
# Mode change baselines both inboxes, without changing any other profile.
check_set '{"profile":"shared","mode":"per_sim","enabled":1,"method":"webhook","webhook_url":"https://shared.example.com/hook"}'
[ "$(cut -d'|' -f1 "$BASE/state")" = 1 ]
[ "$(cut -d'|' -f1 "$BASE/state.sim1")" = 1 ]
read_mode; select_profile shared; load_config
deliver() { printf '%s|%s|%s\n' "${MU300_SIM_SLOT:-0}" "$webhook_url" "$3" >> "$base/deliveries"; DELIVER_RESULT=sent; }
process_first_sim; process_second_sim
[ ! -e "$base/deliveries" ]
old_sms "$ROOT_POOL" 2; old_sms "$ROOT_POOL/sim1" 2
process_first_sim; process_second_sim; process_first_sim; process_second_sim
[ "$(wc -l < "$base/deliveries")" = 2 ]
grep -q '^0|https://sim0.example.com/' "$base/deliveries"
grep -q '^1|https://sim1.example.com/' "$base/deliveries"
# SIM2 still processes when shared is disabled (SIM1 is not a global switch).
check_set '{"profile":"shared","mode":"per_sim","enabled":0,"method":"webhook"}'
old_sms "$ROOT_POOL/sim1" 3
select_profile shared; load_config; read_mode; process_second_sim
[ "$(wc -l < "$base/deliveries")" = 3 ]
# Per-card disable/re-enable must not deliver messages received while disabled.
check_set '{"profile":"sim1","mode":"per_sim","enabled":0,"method":"webhook","webhook_url":"https://sim1.example.com/hook"}'
old_sms "$ROOT_POOL/sim1" 4
check_set '{"profile":"sim1","mode":"per_sim","enabled":1,"method":"webhook","webhook_url":"https://sim1.example.com/hook"}'
select_profile shared; load_config; read_mode; process_second_sim
[ "$(wc -l < "$base/deliveries")" = 3 ]
# JSON/form/URL escaping is one pass: placeholders inside SMS stay literal.
load_config
webhook_url='https://example.com/hook?text={text}&sim={sim}'
webhook_body='{"text":"{text}","nested":{"sim":"{sim}"}}'
webhook_method=POST webhook_content_type=application/json webhook_timeout=10 webhook_headers='Authorization: Bearer TEST_ONLY'
_text='hello "世界" & = + {sim} $(reboot)
second line'
_from=10010 _date=now _kind=sms MU300_SIM_SLOT=1
render_webhook > "$base/render"
body=$(jsonfilter -i "$base/render" -e '@.body')
[ "$(printf '%s' "$body" | jsonfilter -e '@.text')" = "$_text" ]
[ "$(printf '%s' "$body" | jsonfilter -e '@.nested.sim')" = SIM2 ]
url=$(jsonfilter -i "$base/render" -e '@.url')
case "$url" in *'%26%20%3D%20%2B%20%7Bsim%7D'*'sim=SIM2') ;; *) fail 'URL escaping' ;; esac
webhook_content_type=application/x-www-form-urlencoded webhook_body='text={text}&from={from}'
render_webhook > "$base/render"
body=$(jsonfilter -i "$base/render" -e '@.body')
case "$body" in *'%26%20%3D%20%2B%20%7Bsim%7D'*'&from=10010') ;; *) fail 'form escaping' ;; esac
expect_error '{"webhook_timeout":121}'
expect_error '{"webhook_headers":"Host: internal.example.com"}'
expect_error '{"webhook_headers":"X-Test: a\r\nInjected: yes"}'
expect_error '{"webhook_method":"DELETE"}'
expect_error '{"webhook_body":"{broken}"}'
expect_error '{"webhook_url":"https://{text}.example.com/hook"}'
expect_error '{"profile":"../../etc"}'
# A future battery device uses the shared profile even in independent mode.
BATTERY=$MU300_FORWARD_BATTERY
mkdir -p "$BATTERY"
printf '1\n' > "$BATTERY/present"; printf '50\n' > "$BATTERY/capacity"; printf 'Discharging\n' > "$BATTERY/status"
check_set '{"profile":"shared","mode":"per_sim","enabled":1,"method":"webhook","webhook_url":"https://power.example.com/hook","power_forward_enabled":1}'
select_profile shared; load_config; load_state; read_result; process_power
[ "$(wc -l < "$base/deliveries")" = 3 ]
printf 'Charging\n' > "$BATTERY/status"
process_power
grep -q 'https://power.example.com/hook' "$base/deliveries"
# status/history never expose templates, headers, destinations or message text.
status_only sim1 > "$base/status"
! grep -qE 'SECRET|quoted|example.com|TEST_ONLY' "$base/status"
echo 'PASS profiles/secrets/barriers/source-SIM/escaping/validation/power/privacy'
# Restore production delivery, replace ONLY network transports. No sockets open.
. "$base/lib.sh"
resolve_public() { RESOLVE="$1:$2:93.184.216.34"; PICKED_IP=93.184.216.34; }
curl() {
    printf '%s\n' "$@" > "$base/curl.args"
    replyfile=
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --data-binary) shift; cp "${1#@}" "$base/curl.body" ;;
            -H) shift; case "$1" in @*) cp "${1#@}" "$base/curl.headers" ;; esac ;;
            -o) shift; replyfile=$1 ;;
        esac
        shift
    done
    printf '%s' '{"errcode":0}' > "$replyfile"
    printf '%s' "${TEST_HTTP_CODE:-200}"
}
msmtp() { cat > "$base/smtp.body"; }
# Minimal base images may omit openssl; exercise argument/encoding plumbing
# there. On the device the installed openssl performs the actual HMAC/MIME.
if ! command -v openssl >/dev/null 2>&1; then
    openssl() { case "$1" in dgst) cat ;; base64) cat >/dev/null; printf 'VEVTVCs/=' ;; *) return 1 ;; esac; }
fi
load_config
enabled=1 method=webhook webhook_url='https://example.com/hook?from={from}'
webhook_headers='Authorization: Bearer TEST_ONLY'
webhook_body='{"text":"{text}","sim":"{sim}"}'
webhook_timeout=25 webhook_method=POST webhook_content_type=application/json
MU300_SIM_SLOT=1
deliver sms 10010 '"body" & {sim}' now
[ "$DELIVER_RESULT" = sent ] && [ "$HTTP_CODE" = 200 ]
[ "$(jsonfilter -i "$base/curl.body" -e '@.text')" = '"body" & {sim}' ]
[ "$(jsonfilter -i "$base/curl.body" -e '@.sim')" = SIM2 ]
grep -q '^Authorization: Bearer TEST_ONLY$' "$base/curl.headers"
grep -q '^25$' "$base/curl.args"
webhook_method=GET
deliver sms 10010 'body' now
! grep -q '^--data-binary$' "$base/curl.args"
grep -q '^GET$' "$base/curl.args"
TEST_HTTP_CODE=302
if deliver sms 10010 body now; then fail 'redirect accepted'; fi
[ "$DELIVER_RESULT" = delivery_failed ]
TEST_HTTP_CODE=503
if deliver sms 10010 body now; then fail 'server failure accepted'; fi
TEST_HTTP_CODE=200 webhook_method=POST webhook_body=
deliver sms 10010 legacy now
[ "$(jsonfilter -i "$base/curl.body" -e '@.text')" = legacy ]
[ "$(jsonfilter -i "$base/curl.body" -e '@.date')" = now ]
method=dingtalk dingtalk_webhook='https://oapi.dingtalk.com/robot/send?access_token=TEST_ONLY' dingtalk_secret=TEST_SIGN_KEY
deliver sms 10010 body now
grep -q 'timestamp=.*sign=' "$base/curl.args"
[ "$(jsonfilter -i "$base/curl.body" -e '@.msgtype')" = text ]
method=smtp smtp_host=smtp.example.com smtp_port=465 smtp_username=from@example.com smtp_to=to@example.com smtp_password=TEST_ONLY
deliver sms 10010 body now
grep -q 'Subject: =?UTF-8?B?' "$base/smtp.body"
echo 'PASS isolated real delivery: POST/GET/headers/timeout/HTTP errors/legacy JSON/DingTalk signing/SMTP'
# Saving a disabled profile before its inbox exists cannot create a zero/zero
# cursor that would subsequently turn a SIM history import into live mail.
mv "$ROOT_POOL/next_id" "$ROOT_POOL/next_id.fixture-hold"
rm -f "$BASE/state"
check_set '{"profile":"shared","mode":"shared","enabled":0,"method":"webhook"}'
[ ! -e "$BASE/state" ]
mv "$ROOT_POOL/next_id.fixture-hold" "$ROOT_POOL/next_id"
echo 'PASS uninitialized inbox retains first-ready replay barrier'
