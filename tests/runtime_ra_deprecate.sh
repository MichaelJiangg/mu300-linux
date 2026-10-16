#!/bin/sh
# Run ONLY in a disposable OpenWrt container with its own network namespace,
# NET_ADMIN/NET_RAW, ucode-mod-socket, ip-full, tcpdump and coreutils-timeout.
# Use native OpenWrt: QEMU user-mode may reject IPV6_MULTICAST_IF/ethtool ioctls.
# No physical interface.
# /repo is this repository, mounted read-only.
set -eu
[ "${MU300_RA_TEST:-}" = isolated-container ] || exit 2
helper=/repo/openwrt/overlay/opt/mu300/bin/ra-deprecate
ip link add ra-test type veth peer name ra-peer
trap 'ip link del ra-test 2>/dev/null || :' EXIT
ip link set ra-test addrgenmode none
ip link set ra-peer addrgenmode none
ip link set ra-test up
ip link set ra-peer up
ip -6 addr add fe80::1234/64 dev ra-test nodad
ip -6 addr add fe80::5678/64 dev ra-peer nodad
timeout 8 tcpdump -i ra-peer -n -vv -c 1 'icmp6 && ip6[40] == 134' >/tmp/ra-capture 2>/tmp/ra-capture.err &
capture=$!
# Readiness of this test's capture, not a production delay.
for n in $(seq 1 5); do
    grep -q 'listening on' /tmp/ra-capture.err 2>/dev/null && break
    sleep 1
done
ucode "$helper" ra-test 1234 2001:db8:1234:5678::/64
wait "$capture"
cat /tmp/ra-capture
grep -q 'hlim 255' /tmp/ra-capture
grep -q 'fe80::1234 > ff02::1' /tmp/ra-capture
grep -q 'router lifetime 1234s' /tmp/ra-capture
grep -q '2001:db8:1234:5678::/64' /tmp/ra-capture
grep -q 'valid time 7200s, pref. time 0s' /tmp/ra-capture
! grep -q 'bad icmp6 cksum' /tmp/ra-capture
for bad in '2001:db8::1/64' 'fd00::/64' '2001:db8::/48' 'garbage'; do
    if ucode "$helper" ra-test 1234 "$bad" >/dev/null 2>&1; then
        echo "invalid prefix accepted: $bad" >&2
        exit 1
    fi
done
for bad in 0 9001 -1 nope; do
    if ucode "$helper" ra-test "$bad" 2001:db8::/64 >/dev/null 2>&1; then
        echo "invalid lifetime accepted: $bad" >&2
        exit 1
    fi
done
echo 'RA runtime checks passed (isolated veth only)'
