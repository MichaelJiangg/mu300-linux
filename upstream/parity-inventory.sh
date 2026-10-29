#!/bin/sh
# What the running kernel provides, one item per line, for check-parity.py (upstream/parity-5.4.txt). Run as root on
# a board, once under 5.4 and once under a mainline kernel, and keep the output as upstream/parity/BOARD-KERNEL.inv:
#   sudo sh parity-inventory.sh > f50b-5.4.inv
# Items (sorted, no duplicates):
#   driver BUS/NAME     a driver with at least one device bound to it (/sys/bus/*/drivers/*)
#   tz NAME, cooling NAME, devfreq NAME, cpufreq DRIVER, cpuidle STATE
#   psy NAME, typec NAME, extcon NAME, input NAME, led NAME, regulator NAME, misc NAME, hwrng NAME, udc NAME,
#   class NAME          the classes of /sys/class that have a device
# Device names that carry an address (led mmc0::, udc 25100000.dwc3) are kept as they are. Misc devices and classes
# count only with hardware behind them (not /sys/devices/virtual).
# A driver or device whose module is not part of the running kernel's own set (not in /lib/modules/RELEASE nor built
# in: a package that loads its modules from elsewhere) is not the kernel's and is left out.
# POSIX sh and busybox (OpenWrt) alike.
rel=$(uname -r)
known=$( { find "/lib/modules/$rel" -name '*.ko*' 2>/dev/null | sed 's|.*/||; s|\.ko.*$||'
           sed 's|.*/||; s|\.ko$||' "/lib/modules/$rel/modules.builtin" 2>/dev/null; } | tr - _ | sort -u)
# ours PATH: PATH (a driver, or a device's driver) belongs to the kernel - built in, or one of its modules
ours() {
    [ -e "$1/module" ] || return 0
    m=$(readlink "$1/module"); m=${m##*/}
    # built-in code has a /sys/module entry too (for its parameters), without initstate
    [ -e "/sys/module/$m/initstate" ] || return 0
    printf '%s\n' "$known" | grep -qx "$(printf '%s' "$m" | tr - _)"
}
{
for d in /sys/bus/*/drivers/*; do
    bus=${d#/sys/bus/}; bus=${bus%%/*}
    for dev in "$d"/*; do
        [ -L "$dev" ] || continue
        case ${dev##*/} in module|bind|unbind|uevent|new_id|remove_id) continue ;; esac
        [ -d "$dev/." ] || continue
        ours "$d" && echo "driver $bus/${d##*/}"; break
    done
done
for z in /sys/class/thermal/thermal_zone*/type; do [ -f "$z" ] && echo "tz $(cat "$z")"; done
for z in /sys/class/thermal/cooling_device*/type; do [ -f "$z" ] && echo "cooling $(cat "$z")"; done
for p in /sys/devices/system/cpu/cpufreq/policy*/scaling_driver; do [ -f "$p" ] && echo "cpufreq $(cat "$p")"; done
for s in /sys/devices/system/cpu/cpu0/cpuidle/state*/name; do [ -f "$s" ] && echo "cpuidle $(cat "$s")"; done
[ -f /sys/class/misc/hw_random/rng_available ] && for r in $(cat /sys/class/misc/hw_random/rng_available); do echo "hwrng $r"; done
for c in devfreq power_supply typec extcon leds regulator misc udc; do
    for x in /sys/class/$c/*; do
        [ -e "$x" ] || continue
        [ ! -e "$x/device/driver" ] || ours "$x/device/driver" || continue
        # a misc device without hardware behind it (/sys/devices/virtual) is a feature of some module, which the
        # module lists cover - and it cannot be told which module made it
        [ $c != misc ] || case $(readlink -f "$x") in /sys/devices/virtual/*) continue ;; esac
        n=${x##*/}
        [ $c != regulator ] || n=$(cat "$x/name" 2>/dev/null)
        case $c in power_supply) k=psy ;; leds) k=led ;; *) k=$c ;; esac
        [ -n "$n" ] && echo "$k $n"
    done
done
for x in /sys/class/input/input*; do
    [ -f "$x/name" ] || continue
    [ ! -e "$x/device/driver" ] || ours "$x/device/driver" || continue
    # a sound card's jack: its input device hangs off the card, whose driver is the card's
    [ ! -e "$x/device/device/driver" ] || ours "$x/device/device/driver" || continue
    echo "input $(cat "$x/name")"
done
# a class counts when a device with hardware behind it is in it (not only /sys/devices/virtual ones, as for misc)
for c in /sys/class/*; do
    [ -d "$c" ] || continue
    for x in "$c"/*; do
        [ -e "$x" ] || continue
        case $(readlink -f "$x") in /sys/devices/virtual/*) continue ;; esac
        echo "class ${c##*/}"; break
    done
done
} | sed 's/[[:space:]]*$//' | LC_ALL=C sort -u
