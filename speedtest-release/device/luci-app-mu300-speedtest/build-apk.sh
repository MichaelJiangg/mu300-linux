#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ] || [ -z "$1" ]; then
    printf 'Usage: %s LIBRESPEED_ASSET_DIR [OUTPUT_DIR]\n' "$0" >&2
    exit 2
fi

export LC_ALL=C TZ=UTC COPYFILE_DISABLE=1
umask 022

package_dir=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
apk=${APK:-apk}
name=luci-app-mu300-speedtest
version=1.0.0-r13
filename=$name-$version.apk
output_dir=${2:-$package_dir/../../.build/mu300-speedtest}

if ! command -v "$apk" >/dev/null 2>&1; then
    printf 'apk-tools 3 with mkpkg is required. Set APK to its executable path.\n' >&2
    exit 1
fi
if [ "$(id -u)" -ne 0 ] && ! command -v fakeroot >/dev/null 2>&1; then
    printf 'Build as root in an isolated environment or use a dynamic apk with fakeroot.\n' >&2
    exit 1
fi

mkdir -p "$output_dir"
output_dir=$(CDPATH= cd "$output_dir" && pwd -P)
work_dir=$(mktemp -d "$output_dir/.apk-build.XXXXXX")
trap 'rm -rf -- "$work_dir"' EXIT
trap 'exit 1' HUP INT TERM
payload="$work_dir/root"
mkdir -p "$payload/www"
cp -R "$package_dir/root/." "$payload/"
cp -R "$package_dir/htdocs/." "$payload/www/"
sh "$package_dir/stage-assets.sh" "$payload" "$1"

catalog=mu300-speedtest.zh-cn.lmo
catalog_dir="$payload/usr/lib/lua/luci/i18n"
mkdir -p "$catalog_dir"
if [ -s "$package_dir/lmo/$catalog" ]; then
    cp "$package_dir/lmo/$catalog" "$catalog_dir/$catalog"
elif command -v po2lmo >/dev/null 2>&1; then
    po2lmo "$package_dir/po/zh_Hans/mu300-speedtest.po" "$catalog_dir/$catalog"
fi
if [ ! -s "$catalog_dir/$catalog" ]; then
    printf 'Compile the zh_Hans catalog with po2lmo or provide lmo/%s.\n' "$catalog" >&2
    exit 1
fi

# This package contains only web resources and LuCI menu data.
find "$payload" -type d -exec chmod 0755 {} \;
find "$payload" -type f -exec chmod 0644 {} \;
find "$payload" -type f -exec touch -t 202601010000.00 {} \;

# LuCI hashes the menu file's inode, size and mtime to decide when to rebuild its index.
menu_epoch=$((1767225600 + ${version##*-r}))
menu_timestamp=$(date -u -d "@$menu_epoch" +%Y%m%d%H%M.%S 2>/dev/null) ||
    menu_timestamp=$(date -u -r "$menu_epoch" +%Y%m%d%H%M.%S)
touch -t "$menu_timestamp" "$payload/usr/share/luci/menu.d/$name.json"

set -- "$apk" mkpkg \
    --info "name:$name" \
    --info "version:$version" \
    --info 'arch:noarch' \
    --info 'description:Browser network speed test for the MU300 LuCI interface' \
    --info 'depends:luci-base' \
    --compression deflate --files "$payload" --output "$work_dir/$filename"
if [ -n "${APK_SIGN_KEY:-}" ]; then
    set -- "$@" --sign-key "$APK_SIGN_KEY"
fi
if [ "$(id -u)" -ne 0 ]; then
    set -- fakeroot "$@"
fi
"$@"

(
    cd "$work_dir"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$filename"
    else
        shasum -a 256 "$filename"
    fi > "$filename.sha256"
)
mv "$work_dir/$filename" "$work_dir/$filename.sha256" "$output_dir/"
printf '%s\n' "$output_dir/$filename"
