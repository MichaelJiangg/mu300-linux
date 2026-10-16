#!/bin/sh
set -eu
sdk=openwrt-sdk-25.12.5-armsr-armv8_gcc-14.3.0_musl.Linux-x86_64
sdk_sha=1b0316604a3e820b2b008a1baff3f9dac6716af942bef800930e58c7de98c98b
cd /cache
# Serialize the shared SDK when 6.x/7.x rootfs builds run in parallel.
exec 9>/cache/build.lock
flock 9
if [ ! -d "$sdk" ]; then
    if [ ! -s sdk.tar.zst ]; then
        curl -fL --retry 3 -o sdk.tar.zst.part "https://downloads.openwrt.org/releases/25.12.5/targets/armsr/armv8/$sdk.tar.zst"
        echo "$sdk_sha  sdk.tar.zst.part" | sha256sum -c -
        mv sdk.tar.zst.part sdk.tar.zst
    fi
    echo "$sdk_sha  sdk.tar.zst" | sha256sum -c -
    tar --zstd -xf sdk.tar.zst
fi
cd "$sdk"
export FORCE_UNSAFE_CONFIGURE=1
if [ ! -f package/feeds/base/fstools/Makefile ]; then
    ./scripts/feeds update base
    ./scripts/feeds install -p base fstools
fi
# This APK is intentionally tied to the same fstools revision as 25.12.5.
# Fail on a changed feed instead of producing an unreviewed probe binary.
grep -q 'PKG_SOURCE_VERSION:=16718b6e3c0fc7db7be6ae5848db0eae88ac8a8b' package/feeds/base/fstools/Makefile
sed -i 's/^PKG_RELEASE:=.*/PKG_RELEASE:=100/' package/feeds/base/fstools/Makefile
mkdir -p package/feeds/base/fstools/patches
cp /src/patches/fstools-probe-device-types.patch package/feeds/base/fstools/patches/900-mu300-probe-device-types.patch
# Add the tested guard as a source patch too; OpenWrt applies both before CMake.
{
    printf '%s\n' '--- /dev/null' '+++ b/block-probe-guard.h'
    printf '@@ -0,0 +1,%s @@\n' "$(wc -l < /src/block-probe-guard.h)"
    sed 's/^/+/' /src/block-probe-guard.h
} > package/feeds/base/fstools/patches/901-mu300-probe-guard-header.patch
printf '%s\n' 'CONFIG_ALL_NONSHARED=n' 'CONFIG_ALL_KMODS=n' 'CONFIG_ALL=n' \
    'CONFIG_BUILDBOT=n' 'CONFIG_PACKAGE_block-mount=m' 'CONFIG_SIGNED_PACKAGES=n' > .config
make defconfig
make package/fstools/clean
make -j4 package/fstools/compile V=s
apk=$(find bin -name 'block-mount-*-r100.apk' -type f)
[ -n "$apk" ] && [ "$(printf '%s\n' "$apk" | wc -l)" = 1 ] || {
    echo 'expected exactly one patched block-mount APK' >&2; exit 1;
}
cp "$apk" "/out/$OUT_NAME.part"
mv "/out/$OUT_NAME.part" "/out/$OUT_NAME"
sha256sum "/out/$OUT_NAME" | cut -d' ' -f1 > "/out/$OUT_NAME.sha256"
printf '%s\n' "$BUILD_ID" > "/out/$OUT_NAME.build-id"
