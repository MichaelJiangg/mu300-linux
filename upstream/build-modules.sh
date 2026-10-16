#!/bin/bash
# Build vendor modules and collect the kernel's own modules, flat for kmodloader.
# Run inside the mu300-mainline-build container: bash /work/build-modules.sh [module-dir...]
set -eo pipefail
KV=${KV:-6.18.54}
[ "$(uname -m)" = aarch64 ] || export CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
K=/src/linux-$KV
O=/src/out-$KV
OUT=${MU300_OUT_DIR:-/work/${OUTDIR:-out}}   # as in build.sh; keep module-name case
# every out-of-tree module, in dependency order (wlan/bt use wcn_bsp, the PMIC watchdog and Mali the modem's headers)
mods=${*:-wcn_bsp sprd_wlan_combo sprdbt_tty sprd_modem sprd_pmic_wdt mali mu300_thermal}
mkdir -p $OUT/modules
# a full build starts clean, so no module of another kernel release ends up next to the new ones
[ $# -gt 0 ] || rm -f $OUT/modules/*.ko $OUT/modules/*.log
# Module.symvers for the built-in exports (pcie-sprd etc.)
make -C $K O=$O ARCH=arm64 -j"$(nproc)" modules > $O/modules.log 2>&1 || { tail -20 $O/modules.log; exit 1; }
cmp -s "$O/.config" "$OUT/kernel.config" || {
    echo 'kernel configuration changed or Image evidence missing; run build.sh first with the same KV/OUTDIR' >&2
    exit 1
}
# Based on upstream 59e17d5/765da29: =m was previously compiled but never shipped.
# A private staging directory avoids stale modules from a previous configuration.
STAGE=$(mktemp -d "$O/mod-install.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
make -C "$K" O="$O" ARCH=arm64 INSTALL_MOD_PATH="$STAGE" INSTALL_MOD_STRIP=1 DEPMOD=true modules_install >> "$O/modules.log" 2>&1 ||
    { tail -20 "$O/modules.log"; exit 1; }
if [ -f "$OUT/modules.in-tree" ]; then
    while IFS= read -r ko; do
        case $ko in ''|*/*|*..*) echo "invalid previous module name: $ko" >&2; exit 1 ;; esac
        rm -f "$OUT/modules/$ko"
    done < "$OUT/modules.in-tree"
fi
find "$STAGE/lib/modules" -name '*.ko' -printf '%f\n' | sort > "$OUT/modules.in-tree"
tr - _ < "$OUT/modules.in-tree" | sort > "$O/modules.in-tree.names"
[ -z "$(uniq -d "$O/modules.in-tree.names")" ] || { echo 'in-tree module name collision' >&2; exit 1; }
find "$STAGE/lib/modules" -name '*.ko' -exec cp {} "$OUT/modules/" \;
extra=
for m in $mods; do
    rm -rf /src/mod-build/$m && mkdir -p /src/mod-build && cp -r /work/modules/$m /src/mod-build/$m
    # wlan/bt use wcn_bsp's exports and its vendor headers (../wcn_bsp/kinclude)
    [ -d /src/mod-build/wcn_bsp ] || cp -r /work/modules/wcn_bsp /src/mod-build/wcn_bsp
    # the PMIC watchdog talks to pm_sys over SIPC, so it needs the modem stack's headers next to it
    [ -d /src/mod-build/sprd_modem ] || cp -r /work/modules/sprd_modem /src/mod-build/sprd_modem
    # the Mali DDK needs its own configuration switches (same ones the 5.4 build uses)
    margs=
    kcflags=
    [ "$m" = mali ] && kcflags="-I/src/mod-build/mali/kinclude"
    # the Mali driver calls Trusty for protected mode, so it needs the vendor trusty headers that ship with
    # the modem modules
    [ "$m" = mali ] && [ ! -d /src/mod-build/mali/kinclude ] && cp -r /work/modules/sprd_modem/kinclude /src/mod-build/mali/kinclude
    [ "$m" = mali ] && margs="src=/src/mod-build/mali CONFIG_MALI_MIDGARD=m CONFIG_MALI_PLATFORM_NAME=qogirn6pro CONFIG_MALI_DEVFREQ=y CONFIG_DEVFREQ_THERMAL=y CONFIG_MALI_DEBUG=n CONFIG_MALI_FENCE_DEBUG=n BUILD=no"
    make -C $O ARCH=arm64 M=/src/mod-build/$m KBUILD_EXTRA_SYMBOLS="$extra" KCFLAGS="$kcflags" $margs -j"$(nproc)" modules 2>&1 | tee $OUT/modules/$m.log
    [ -f /src/mod-build/$m/Module.symvers ] && extra="$extra /src/mod-build/$m/Module.symvers"
    while IFS= read -r ko; do
        name=$(basename "$ko" | tr - _)
        ! grep -Fqx "$name" "$O/modules.in-tree.names" || { echo "vendor/in-tree module collision: $name" >&2; exit 1; }
        cp "$ko" "$OUT/modules/"
        # Keep compact .BTF/.BTF.ext but do not ship multi-megabyte DWARF
        # from vendor modules now that DEBUG_INFO_BTF_MODULES is enabled.
        "${CROSS_COMPILE:-}strip" --strip-debug "$OUT/modules/$(basename "$ko")"
    done < <(find /src/mod-build/$m -name '*.ko')
done
# Evidence covers every module (including vendor dependencies), not just a shortlist.
if grep -qx 'CONFIG_DEBUG_INFO_BTF_MODULES=y' "$OUT/kernel.config"; then
    # A missing vmlinux can silently skip external-module BTF generation.
    # Verify the actual stripped payload rather than trusting Kconfig alone.
    for ko in "$OUT"/modules/*.ko; do
        # Consume all output: grep -q can SIGPIPE readelf under pipefail.
        "${CROSS_COMPILE:-}readelf" -SW "$ko" | grep -E '\.BTF[[:space:]]+PROGBITS' >/dev/null || {
            echo "BTF missing from built module: $ko" >&2; exit 1;
        }
    done
fi
(cd "$OUT" && sha256sum Image kernel.config modules/*.ko > modules.sha256)
python3 /work/check-container-support.py "$OUT"
ls -la $OUT/modules/*.ko
