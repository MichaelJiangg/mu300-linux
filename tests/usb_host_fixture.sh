#!/bin/sh
# Run on OpenWrt with real ash/UCI/jsonfilter/flock. All UCI, sysfs and ip
# targets are isolated; never changes a production interface or role.
set -eu
USB=$1
export REAL_UCI=$(command -v uci)
export FIXTURE=$(mktemp -d /tmp/mu300-usb-host-test.XXXXXX)
mkdir -p "$FIXTURE/config" "$FIXTURE/delta" "$FIXTURE/bin" "$FIXTURE/net" "$FIXTURE/usb1"
printf 'config device usb\n' > "$FIXTURE/config/unisoc_modem"
printf "config device lanbr\n option name 'br-lan'\n option type 'bridge'\n list ports 'usb0'\nconfig interface wan\n option device 'eth1'\n" > "$FIXTURE/config/network"
printf '#!/bin/sh\ncase "$*" in *"commit network"*) [ ! -f "$FIXTURE/fail-commit" ] || exit 1 ;; esac\nexec "$REAL_UCI" -c "$FIXTURE/config" -t "$FIXTURE/delta" "$@"\n' > "$FIXTURE/bin/uci"
printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "$FIXTURE/ip-calls"\n' > "$FIXTURE/bin/ip"
printf '#!/bin/sh\nprintf '\''{"interface":[{"device":"sipa_eth0","l3_device":"sipa_eth0"}]}\\n'\''\n' > "$FIXTURE/bin/ubus"
chmod 755 "$FIXTURE/bin/uci" "$FIXTURE/bin/ip" "$FIXTURE/bin/ubus"
export PATH="$FIXTURE/bin:$PATH"
export MU300_USB_ROLE_FILE="$FIXTURE/role"
export MU300_USB_NET_CLASS="$FIXTURE/net"
export MU300_USB_NET_LOCK="$FIXTURE/net.lock"
export MU300_USB_IP_BIN="$FIXTURE/bin/ip"
export MU300_USB_BOOT_FILE="$FIXTURE/boot.conf"
export MU300_USB_ROLE_STATE="$FIXTURE/role-state"
export MU300_USB_GADGET_DIR="$FIXTURE/gadgets"
export MU300_USB_NETWORK_SERVICE=/bin/false
printf 'host\n' > "$MU300_USB_ROLE_FILE"
for name in eth0 eth1 wlan1; do
    mkdir -p "$FIXTURE/net/$name" "$FIXTURE/usb1/$name"
    ln -s "$FIXTURE/usb1/$name" "$FIXTURE/net/$name/device"
    printf '1\n' > "$FIXTURE/net/$name/type"
    printf '02:11:22:33:44:55\n' > "$FIXTURE/net/$name/address"
done
mkdir "$FIXTURE/net/wlan1/wireless"
"$USB" get | jsonfilter -e '@.lan_auto' | grep -qx 0
"$USB" net-sync
[ "$(uci -q get network.lanbr.ports)" = usb0 ]
"$USB" set-lan-auto 1 | jsonfilter -e '@.ok' | grep -qx 1
"$USB" net-list > "$FIXTURE/list.json"
[ "$(jsonfilter -i "$FIXTURE/list.json" -e '@.devices[*].name' | wc -l)" -eq 2 ]
[ "$(jsonfilter -i "$FIXTURE/list.json" -e '@.devices[1].eligible')" = 0 ]
[ "$(jsonfilter -i "$FIXTURE/list.json" -e '@.devices[1].owner')" = network.wan ]
[ "$(uci -q get network.lanbr.ports)" = usb0 ]
# A failed commit does not leak pending additions into default UCI staging.
touch "$FIXTURE/fail-commit"
"$USB" net-sync
[ "$(uci -q get network.lanbr.ports)" = usb0 ]
[ -z "$(uci -q changes network)" ]
rm "$FIXTURE/fail-commit"
# Parallel kernel events serialize and add a port only once.
"$USB" net-sync & first=$!
"$USB" net-sync & second=$!
wait "$first"; wait "$second"
[ "$(uci -q get network.lanbr.ports)" = 'usb0 eth0' ]
[ "$(grep -c 'dev eth0 master br-lan' "$FIXTURE/ip-calls")" -eq 2 ]
! grep -q 'dev eth1' "$FIXTURE/ip-calls"
! grep -q 'dev wlan1' "$FIXTURE/ip-calls"
"$USB" set-lan-auto 0 | jsonfilter -e '@.ok' | grep -qx 1
printf '' > "$FIXTURE/ip-calls"
printf 'device\n' > "$MU300_USB_ROLE_FILE"
"$USB" net-sync
grep -q 'dev eth0 master br-lan' "$FIXTURE/ip-calls"
[ "$(uci -q get network.lanbr.ports)" = 'usb0 eth0' ]
printf 'USB_HOST_FIXTURE_OK %s\n' "$FIXTURE"
