#!/bin/sh
# File-backed modem for replay_fixture.sh only. No serial devices or sockets.
set -eu
: "${REPLAY_FIXTURE:?isolated fixture directory required}"
for command do :; done
printf '%s\n' "$command" >> "$REPLAY_FIXTURE/commands"
fault=${REPLAY_TEST_FAULT:-}
[ "$fault" != silent ] || exit 1
case $command in
    AT) echo OK; exit 0 ;;
    'AT+SPTESTMODE?') key=tm; label=SPTESTMODE ;;
    'AT+SP5GRAN?') key=gran; label=SP5GRAN ;;
    'AT+SPENDC?') key=endc; label=ENDC ;;
    AT+SPLBAND=0) key=lte; label=SPLBAND ;;
    AT+SPLBAND=3) key=nr; label=SPLBAND ;;
    'AT+CFUN?') key=cfun; label=CFUN ;;
    AT+SPFORCEFRQ=12,3) key=cell12; label=SPFORCEFRQ ;;
    AT+SPFORCEFRQ=16,3) key=cell16; label=SPFORCEFRQ ;;
    *) key= ;;
esac
if [ -n "$key" ]; then
    value=$(cat "$REPLAY_FIXTURE/modem/$key")
    printf '+%s: %s\nOK\n' "$label" "$value"
    exit 0
fi
case "$fault:$command" in
    reject:*|restart:AT+SFUN=*) echo ERROR; exit 0 ;;
    ignore:*) echo OK; exit 0 ;;
esac
case $command in
    AT+SPTESTMODE=*) printf '%s' "${command#*=}" > "$REPLAY_FIXTURE/modem/tm" ;;
    AT+SP5GRAN=*) printf '%s' "${command#*=}" > "$REPLAY_FIXTURE/modem/gran" ;;
    AT+SPENDC=*) value=${command#*=}; [ "$value" != 2 ] || value=0; printf '%s' "$value" > "$REPLAY_FIXTURE/modem/endc" ;;
    AT+SPLBAND=1,*) printf '%s' "${command#*,}" > "$REPLAY_FIXTURE/modem/lte" ;;
    AT+SPLBAND=2,*) printf '%s' "${command#*,}" > "$REPLAY_FIXTURE/modem/nr" ;;
    AT+SPFORCEFRQ=12,4) printf '12,3' > "$REPLAY_FIXTURE/modem/cell12" ;;
    AT+SPFORCEFRQ=16,4) printf '16,3' > "$REPLAY_FIXTURE/modem/cell16" ;;
    AT+SPFORCEFRQ=12,6,*) printf ',%s' "${command#AT+SPFORCEFRQ=12,6,}" >> "$REPLAY_FIXTURE/modem/cell12" ;;
    AT+SPFORCEFRQ=16,6,*) printf ',%s' "${command#AT+SPFORCEFRQ=16,6,}" >> "$REPLAY_FIXTURE/modem/cell16" ;;
    AT+SFUN=5) printf 0 > "$REPLAY_FIXTURE/modem/cfun" ;;
    AT+SFUN=4)
        printf 1 > "$REPLAY_FIXTURE/modem/cfun"
        [ "$fault" != drift ] || printf '0,0,0,0,0' > "$REPLAY_FIXTURE/modem/lte"
        ;;
    *) echo ERROR; exit 1 ;;
esac
[ "$fault" != omit-ok ] || exit 1
echo OK
