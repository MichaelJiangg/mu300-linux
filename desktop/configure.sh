# Sourced only by the desktop copy of android-install.sh.
desktop_configure() {
    . "$P/desktop-settings.env"
    if [ -n "$SSID" ]; then
        printf 'SSID=%s\nPSK=%s\nBAND=5\nCHANNEL=auto\nCOUNTRY=TR\n' "$SSID" "$WIFI_KEY" > "$1/etc/mu300/hotspot.conf"
        chmod 600 "$1/etc/mu300/hotspot.conf"
    fi
    if [ -n "$APN" ]; then
        mkdir -p "$1/etc/uci-defaults"
        printf '#!/bin/sh\nuci set network.wan.apn=%s\nuci commit network\n' "$APN" > "$1/etc/uci-defaults/99-desktop-apn"
        chmod 755 "$1/etc/uci-defaults/99-desktop-apn"
    fi
    echo sd > "$1/etc/mu300/desktop-mode"
}
