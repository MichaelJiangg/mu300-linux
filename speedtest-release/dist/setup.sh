#!/bin/sh
set -eu

package=luci-app-mu300-speedtest
version=1.0.0-r13
filename=$package-$version.apk
sha256=9f586638e1be7b594b0584aa1499a3311dde2bc7bacee2382ad7e7e9aed0e408
bytes=31208
url=https://raw.githubusercontent.com/MichaelJiangg/mu300-linux/speedtest-v1.0.0-r13/speedtest-release/dist/$filename

fail() {
    printf 'SpeedTest install: %s\n' "$*" >&2
    exit 1
}

[ "$#" -eq 0 ] || fail 'Run without arguments on the U30 Air OpenWrt system.'
[ "$(id -u)" = 0 ] || fail 'Run as root on the U30 Air OpenWrt system.'
[ -r /etc/openwrt_release ] && [ -r /etc/mu300/image-version ] ||
    fail 'This is not a supported MU300 OpenWrt installation.'
[ -r /www/cgi-bin/luci ] && [ -d /usr/share/luci/menu.d ] ||
    fail 'The MU300 LuCI panel is required.'

for command in apk curl sha256sum mktemp mu300-user-packages awk; do
    command -v "$command" >/dev/null 2>&1 || fail "Missing command: $command"
done
apk info -e luci-base >/dev/null 2>&1 || fail 'Install the MU300 LuCI panel first.'
mu300-user-packages keep >/dev/null 2>&1 ||
    fail 'This MU300 firmware cannot retain a local APK across updates.'
installed_list=$(apk list --installed --manifest "$package") ||
    fail 'Cannot read installed packages.'
installed_version=$(printf '%s\n' "$installed_list" | awk -v name="$package" '$1 == name { print $2; exit }')
if [ -n "$installed_version" ]; then
    relation=$(apk version -t "$installed_version" "$version") ||
        fail 'Cannot compare package versions.'
    case "$relation" in
        '>')
            fail "Newer SpeedTest $installed_version is already installed." ;;
        '='|'<') ;;
        *) fail 'Cannot interpret the installed package version.' ;;
    esac
fi

umask 077
temp_dir=$(mktemp -d /tmp/mu300-speedtest.XXXXXX) || fail 'Cannot create a temporary directory.'
apk_file=$temp_dir/$filename
trap 'rm -f "$apk_file"; rmdir "$temp_dir" 2>/dev/null || true' 0
trap 'exit 1' 1 2 3 15

printf 'Downloading %s from the pinned GitHub release...\n' "$filename"
curl -fL --connect-timeout 15 --max-time 180 -o "$apk_file" "$url" ||
    fail 'Download failed; the package was not installed.'
[ "$(wc -c < "$apk_file" | tr -d '[:space:]')" = "$bytes" ] ||
    fail 'Downloaded package size differs; the package was not installed.'
actual_sha256=$(sha256sum "$apk_file" | cut -d ' ' -f1)
[ "$actual_sha256" = "$sha256" ] ||
    fail 'Downloaded package SHA-256 differs; the package was not installed.'

apk add --no-network --allow-untrusted "$apk_file" ||
    fail 'The verified package could not be installed.'
installed_list=$(apk list --installed --manifest "$package") ||
    fail 'Cannot verify the installed package.'
installed_version=$(printf '%s\n' "$installed_list" | awk -v name="$package" '$1 == name { print $2; exit }')
[ "$installed_version" = "$version" ] ||
    fail "Expected SpeedTest $version, found ${installed_version:-none}."
[ -r /usr/share/luci/menu.d/luci-app-mu300-speedtest.json ] &&
[ -r /www/luci-static/resources/view/mu300-speedtest-r13.js ] ||
    fail 'The installed LuCI files are missing.'
mu300-user-packages keep "$apk_file" ||
    fail 'The package was installed, but update restoration could not be registered.'

printf 'SpeedTest %s is installed. Open LuCI: Services -> SpeedTest.\n' "$version"
