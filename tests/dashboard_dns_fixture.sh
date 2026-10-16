#!/bin/sh
# Run with OpenWrt's real jsonfilter; does not touch networking or AT.
set -eu
info=${1:?dashboard-info path required}
command -v jsonfilter >/dev/null
eval "$(sed -n '/^wan_dns_servers() {/,/^}/p' "$info")"
check() {
    expected=$1; shift
    actual=$(wan_dns_servers "$@")
    [ "$actual" = "$expected" ] || {
        printf 'DNS mismatch: expected <%s>, got <%s>\n' "$expected" "$actual" >&2
        exit 1
    }
}
wan='{
  "up": true,
  "dns-server": [
    "58.20.127.238",
    "58.20.127.170"
  ],
  "inactive": {"dns-server": ["192.0.2.99"]}
}'
check '58.20.127.238, 58.20.127.170' "$wan" ''
check '58.20.127.238, 58.20.127.170, 2001:db8::53' "$wan" \
    '{"dns-server":["58.20.127.238","2001:db8::53","2001:db8::53"]}'
check '2001:db8::53' '{"dns-server":[]}' '{"dns-server":["2001:db8::53"]}'
check '2001:db8::53' 'invalid JSON' '{"dns-server":["2001:db8::53"]}'
check '' '' ''
check '' '{"dns-server":[]}' '{"inactive":{"dns-server":["192.0.2.99"]}}'
check '' '{"dns-server":null}' '{}'
check '1.1.1.1, 2606:4700:4700::1111' '{"dns-server":["1.1.1.1","2606:4700:4700::1111"]}'
echo 'PASS dashboard DNS: multiline/compact, IPv4/IPv6, dedup, missing, malformed, inactive excluded'
