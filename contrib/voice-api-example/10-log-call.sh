#!/bin/sh
# Example hook for mu300-voice watch: one syslog line per call event, the number masked.
#   sudo install -o root -g root -m 755 10-log-call.sh /etc/mu300/voice.d/10-log-call.sh
# Hooks run as root, so a hook (and /etc/mu300/voice.d) must be root's and writable by nobody else, or it is not
# run. Environment: CALL_EVENT=call, CALL_STATE (incoming waiting dialing alerting active held ended),
# CALL_PREV_STATE (none for a new call), CALL_ID, CALL_DIR (in|out), NUMBER (empty when hidden), CALL_JSON.
# stdin, stdout and stderr are /dev/null, and a hook that takes more than 30 s is stopped.
n=$(printf '%s' "${NUMBER:-hidden}" | sed 's/^\(+\{0,1\}[0-9]\{0,2\}\).*\([0-9][0-9]\)$/\1********\2/')
logger -t mu300-voice-hook "call $CALL_ID ($CALL_DIR): $CALL_PREV_STATE -> $CALL_STATE, $n"
