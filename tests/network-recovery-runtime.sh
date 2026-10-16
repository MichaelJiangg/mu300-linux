#!/bin/sh
set -eu
mkdir -p /var/run /etc/config /run/mu300-registration
printf "config settings 'main'\n option data_sim '1'\n" > /etc/config/unisoc_modem
/sbin/ubusd &
bus_pid=$!
trap 'kill "$bus_pid" 2>/dev/null || true' EXIT
sleep 1
/usr/bin/ucode /opt/mu300/bin/mu300-network-recovery > /tmp/recovery.log 2>&1 &
pid=$!
sleep 1
kill -0 "$pid" || { cat /tmp/recovery.log; exit 1; }
ubus send mu300.registration '{"slot":1}'
ubus send network.interface '{"interface":"wan","action":"ifdown"}'
sleep 1
kill -0 "$pid" || { cat /tmp/recovery.log; exit 1; }
kill -TERM "$pid"
wait "$pid"
test ! -s /tmp/recovery.log || { cat /tmp/recovery.log; exit 1; }
echo 'PASS: actual ubus event listeners, uloop timer and graceful stop'
