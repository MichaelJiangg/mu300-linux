#!/bin/sh
# Build a patched OpenWrt APK, not an LD_PRELOAD workaround or UI-only filter.
# The SDK cache is separate from the kernel build. No kernel rebuild is needed.
set -eu
TOP=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-$TOP/work/block-mount-mu300.apk}
mkdir -p "$(dirname "$OUT")"
OUT=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")
stamp=$(cat "$TOP/openwrt/block-mount.Dockerfile" "$TOP/openwrt/build-block-mount.sh" \
    "$TOP/openwrt/build-block-mount-inner.sh" "$TOP/openwrt/block-probe-guard.h" \
    "$TOP/openwrt/patches/fstools-probe-device-types.patch" | sha256sum | cut -d' ' -f1)
if [ -s "$OUT" ] && [ -s "$OUT.build-id" ] && [ -s "$OUT.sha256" ] &&
   [ "$(cat "$OUT.build-id")" = "$stamp" ] &&
   [ "$(sha256sum "$OUT" | cut -d' ' -f1)" = "$(cat "$OUT.sha256")" ]; then
    echo "block-mount: verified patched APK cache"
    exit 0
fi
docker build --platform linux/amd64 -t mu300-block-sdk-build -f "$TOP/openwrt/block-mount.Dockerfile" "$TOP/openwrt"
# A named volume keeps SDK builds off slow Windows bind mounts. An explicit
# cache directory can also be supplied by Linux/WSL developers.
cache=${MU300_BLOCK_SDK_CACHE:-mu300-block-sdk-25.12.5}
docker run --rm --platform linux/amd64 -v "$cache:/cache" -v "$TOP/openwrt:/src:ro" \
    -v "$(dirname "$OUT"):/out" -e "OUT_NAME=$(basename "$OUT")" -e "BUILD_ID=$stamp" \
    mu300-block-sdk-build sh /src/build-block-mount-inner.sh
