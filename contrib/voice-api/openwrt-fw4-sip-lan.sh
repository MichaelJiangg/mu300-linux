#!/bin/sh
# A SIP server's ports, for the LAN only (OpenWrt, fw4). Run once on the device:  sh openwrt-fw4-sip-lan.sh
# (again after changing the ports below: it replaces its own rules, found by name, and touches nothing else).
#
# fw4's lan zone takes input already and its wan zone (the cellular link, and wlan0 as a Wi-Fi uplink) rejects it,
# so these rules change nothing today: they write the intent down, and keep the server reachable if the lan zone
# is ever set to reject. There is deliberately no rule with src 'wan' or '*' - never open these ports there.
# The ports are dikecphone's sipserver; change them to your server's.
set -eu
SIP_PORTS='5060'
TCP_PORTS='5080 8088'
RTP_PORTS='20000-20200 20400-20800'

for name in mu300-voice-sip mu300-voice-tcp mu300-voice-rtp; do
	while s=$(uci -q show firewall | sed -n "s/^\(firewall\.@rule\[[0-9]*\]\)\.name='$name'$/\1/p" | head -1); [ -n "$s" ]; do
		uci delete "$s"
	done
done

add_rule() {	# add_rule NAME PROTO PORTS
	r=$(uci add firewall rule)
	uci set firewall.$r.name="$1"
	uci set firewall.$r.src='lan'
	uci set firewall.$r.proto="$2"
	uci set firewall.$r.dest_port="$3"
	uci set firewall.$r.target='ACCEPT'
}
add_rule mu300-voice-sip 'tcp udp' "$SIP_PORTS"
add_rule mu300-voice-tcp 'tcp' "$TCP_PORTS"
add_rule mu300-voice-rtp 'udp' "$RTP_PORTS"
uci commit firewall
/etc/init.d/firewall reload
# The same rules as /etc/config/firewall text, for reference:
#   config rule
#       option name 'mu300-voice-sip'
#       option src 'lan'
#       option proto 'tcp udp'
#       option dest_port '5060'
#       option target 'ACCEPT'
