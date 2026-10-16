#!/bin/sh
set -eu
mkdir -p /var/run /etc/config /run/mu300-registration
mkdir -p /opt/mu300/bin
cat > /opt/mu300/bin/mu300-at <<'EOF'
#!/bin/sh
printf '%s\n' "$MU300_AT_DIR:$*" >> /tmp/sim-event-at
printf '+CPIN: READY\nOK\n'
EOF
chmod +x /opt/mu300/bin/mu300-at
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
ubus send mu300.sim-change '{"slot":1}'
ubus send mu300.sim-change '{"slot":"0;bad"}'
ubus send mu300.sim-state '{"slot":1}'
sleep 1
test ! -e /tmp/sim-event-at  # initialization has not completed
touch /run/mu300-ril-handshake
ubus send mu300.sim-state '{"slot":1}'
sleep 1
kill -0 "$pid" || { cat /tmp/recovery.log; exit 1; }
grep -q '/run/mu300-at4:.*SPACTCARD=1;+CPIN?' /tmp/sim-event-at
test "$(wc -l < /tmp/sim-event-at)" = 1
kill -TERM "$pid"
wait "$pid"
test ! -s /tmp/recovery.log || { cat /tmp/recovery.log; exit 1; }
echo 'PASS: actual ubus event listeners, uloop timer and graceful stop'
