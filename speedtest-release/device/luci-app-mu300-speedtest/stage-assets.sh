#!/bin/sh
set -eu

if [ "$#" -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
    printf 'Usage: %s PACKAGE_ROOT LIBRESPEED_ASSET_DIR\n' "$0" >&2
    exit 2
fi

case "$1" in
    /*) package_root=$1 ;;
    *) package_root=$PWD/$1 ;;
esac

repo_root=$(CDPATH= cd "$(dirname "$0")/../.." && pwd -P)
engine_dir=$(CDPATH= cd "$2" && pwd -P)
ui_dir="$repo_root/opendesign/mockups/u30-speedtest"
resource_dir="$package_root/www/luci-static/resources/mu300-speedtest/r13"

# The caller supplies the pinned LibreSpeed build and its accompanying license.
for asset in "$ui_dir/index.html" "$ui_dir/app.js" "$ui_dir/node-selection.js" "$ui_dir/speedtest.css" \
    "$engine_dir/speedtest.js" "$engine_dir/speedtest_worker.js" "$engine_dir/LICENSE"; do
    if [ ! -f "$asset" ] || [ ! -r "$asset" ] || [ ! -s "$asset" ]; then
        printf 'Missing, unreadable, or empty asset: %s\n' "$asset" >&2
        exit 1
    fi
done

if ! live_index=$(awk '
    sub(/data-mode="preview"/, "data-mode=\"live\"") { modes++ }
    /^[[:space:]]*<script src="app[.]js" defer><\/script>[[:space:]]*$/ {
        match($0, /^[[:space:]]*/)
        print substr($0, 1, RLENGTH) "<script src=\"speedtest.js\" defer></script>"
        apps++
    }
    { print }
    END { if (modes != 1 || apps != 1) exit 1 }
' "$ui_dir/index.html"); then
    printf 'Expected a preview mode marker and one app.js script in %s\n' "$ui_dir/index.html" >&2
    exit 1
fi

umask 022
mkdir -p "$resource_dir"
install -m 0644 "$ui_dir/app.js" "$ui_dir/node-selection.js" "$ui_dir/speedtest.css" \
    "$engine_dir/speedtest.js" "$engine_dir/speedtest_worker.js" "$engine_dir/LICENSE" "$resource_dir/"
printf '%s\n' "$live_index" > "$resource_dir/index.html"
chmod 0644 "$resource_dir/index.html"
