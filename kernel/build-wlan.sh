#!/bin/bash
# Build sprd_wlan_combo (SC2355 Wi-Fi) as an external module against out-linux.
# Source: realme C51/C53 AndroidT kernel_modules/kernel5.4/wcn/wlan/wlan_combo (GPL), patched for the MU300.
set -e
WSRC=${WSRC:-/src/ext-wlan_combo}
# build-all.sh hands over a tree that already carries the patches (.mu300-patches); a tree prepared by hand (BUILD.md)
# gets them here, in order, and a patch that does not apply stops the build (as upstream/build.sh). A tree whose marker
# names another patch set was patched before the patches changed: building it would ship the old ones under the new
# name, so it stops (kanoqwq f0926715). build-all.sh makes such a tree again from the pristine sources.
cd "$WSRC"
sum=$(cat /work/patches/wlan_combo-*.patch | sha256sum | cut -d" " -f1)
if [ -f .mu300-patches ]; then
    [ "$(cat .mu300-patches)" = "$sum" ] ||
        { echo "$WSRC carries another set of Wi-Fi patches: run kernel/build-all.sh (it starts from pristine sources)" >&2; exit 1; }
else
    for p in /work/patches/wlan_combo-*.patch; do patch -p1 -s -f < "$p"; done
    echo "$sum" > .mu300-patches
fi
cd /src/zte-u30air
make O=/src/out-linux ARCH=arm64 LLVM=1 LLVM_IAS=1 CC=clang LD=ld.lld -j"$(nproc)" M="$WSRC" modules
llvm-strip --strip-debug -o /src/out-linux/sprd_wlan_combo.ko "$WSRC/sprd_wlan_combo.ko"
