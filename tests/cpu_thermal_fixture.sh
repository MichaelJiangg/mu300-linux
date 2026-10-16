#!/bin/sh
# Isolated filesystem only; no live thermal, CPU or modem access.
set -eu
lib=$1
base=$(mktemp -d /tmp/mu300-thermal-test.XXXXXX)
export MU300_CPU_SYS=$base/cpu MU300_THERMAL_SYS=$base/thermal
export MU300_CPU_CONFIG=$base/config.json MU300_CPU_DEFAULTS=$base/defaults.json MU300_CPU_BOOT_ID=$base/boot
mkdir -p "$MU300_CPU_SYS" "$MU300_THERMAL_SYS"
p=$MU300_CPU_SYS/policy0
mkdir -p "$p"
printf '0 1 2 3\n' > "$p/affected_cpus"
printf 'test\n' > "$p/scaling_driver"
printf 'schedutil performance\n' > "$p/scaling_available_governors"
printf 'schedutil\n' > "$p/scaling_governor"
printf '100\n' > "$p/scaling_min_freq"
printf '300\n' > "$p/scaling_max_freq"
printf '100\n' > "$p/cpuinfo_min_freq"
printf '300\n' > "$p/cpuinfo_max_freq"
printf '100 200 300\n' > "$p/scaling_available_frequencies"
printf 'boot-one\n' > "$base/boot"
# Baseline before a deferred virtual sensor probes; merge it before first edit.
ucode "$lib" boot >/dev/null
z=$MU300_THERMAL_SYS/thermal_zone19
c=$MU300_THERMAL_SYS/cooling_device0
mkdir -p "$z" "$c"
printf 'soc-thmzone\n' > "$z/type"
printf '42000\n' > "$z/temp"
printf 'enabled\n' > "$z/mode"
printf 'step_wise\n' > "$z/policy"
printf 'cpufreq-cpu0\n' > "$c/type"
printf '0\n' > "$c/cur_state"
printf '9\n' > "$c/max_state"
ln -s "$c" "$z/cdev0"
printf '1\n' > "$z/cdev0_trip_point"
for i in 0 1 2; do
    printf '1000\n' > "$z/trip_point_${i}_hyst"
    printf 'passive\n' > "$z/trip_point_${i}_type"
done
printf 'critical\n' > "$z/trip_point_2_type"
printf '70000\n' > "$z/trip_point_0_temp"
printf '85000\n' > "$z/trip_point_1_temp"
printf '110000\n' > "$z/trip_point_2_temp"
call() { ucode "$lib" "$@"; }
check() { jsonfilter -s "$1" -e "$2"; }
out=$(call get)
test "$(check "$out" '@.zones[0].trips[0].writable')" = true
test "$(check "$out" '@.zones[0].trips[0].throttles_cpu')" = false
test "$(check "$out" '@.zones[0].trips[1].throttles_cpu')" = true
test "$(check "$out" '@.zones[0].trips[2].writable')" = false
test "$(jsonfilter -i "$base/defaults.json" -e '@.thermal[*].zone' | wc -l)" = 0
call boot >/dev/null
for entry in \
    '{"zone":"soc-thmzone","trip":2,"temp":90000}' \
    '{"zone":"soc-thmzone","trip":0,"temp":85000}' \
    '{"zone":"soc-thmzone","trip":1,"temp":70000}' \
    '{"zone":"soc-thmzone","trip":1,"temp":101000}' \
    '{"zone":"soc-thmzone","trip":0,"temp":39000}' \
    '{"zone":"soc-thmzone","trip":0,"temp":70500}' \
    '{"zone":"../soc-thmzone","trip":0,"temp":71000}' \
    '{"zone":"soc-thmzone","trip":0,"temp":"71000"}'; do
    if printf '{"scope":"thermal","thermal":[%s],"persist":false}' "$entry" | call apply > "$base/result"; then echo "accepted invalid $entry"; exit 1; fi
    test "$(cat "$z/trip_point_0_temp")" = 70000
    test "$(cat "$z/trip_point_1_temp")" = 85000
done
payload='{"scope":"thermal","thermal":[{"zone":"soc-thmzone","trip":0,"temp":69000},{"zone":"soc-thmzone","trip":1,"temp":84000}],"persist":true}'
printf '%s' "$payload" | call apply > "$base/result"
test "$(cat "$z/trip_point_0_temp")" = 69000
test -f "$base/config.json"
printf '70000\n' > "$z/trip_point_0_temp"
printf '85000\n' > "$z/trip_point_1_temp"
printf 'boot-two\n' > "$base/boot"
call boot >/dev/null
test "$(cat "$z/trip_point_1_temp")" = 84000
printf '{"scope":"thermal","reset":true}' | call apply >/dev/null
test "$(cat "$z/trip_point_0_temp")" = 70000
test "$(cat "$z/trip_point_1_temp")" = 85000
test ! -f "$base/config.json"
# A persistence failure rolls all thermal writes back.
if printf '%s' "$payload" | MU300_CPU_CONFIG="$base/missing/config" call apply > "$base/result"; then exit 1; fi
test "$(jsonfilter -i "$base/result" -e '@.rollback')" = true
test "$(cat "$z/trip_point_0_temp")" = 70000
test "$(cat "$z/trip_point_1_temp")" = 85000
# No CPU binding => read-only. Duplicate names => refuse ambiguous writes.
mv "$z/cdev0" "$z/hidden-cdev"
out=$(call get)
test "$(check "$out" '@.zones[0].trips[0].writable')" = false
if printf '%s' "$payload" | call apply >/dev/null; then exit 1; fi
mv "$z/hidden-cdev" "$z/cdev0"
printf 'disabled\n' > "$z/mode"
if printf '%s' "$payload" | call apply >/dev/null; then exit 1; fi
printf 'enabled\n' > "$z/mode"
mkdir "$MU300_THERMAL_SYS/thermal_zone20"
printf 'soc-thmzone\n' > "$MU300_THERMAL_SYS/thermal_zone20/type"
if printf '%s' "$payload" | call apply >/dev/null; then exit 1; fi
test "$(cat "$z/trip_point_2_temp")" = 110000
test "$(cat "$z/trip_point_1_hyst")" = 1000
rm "$MU300_THERMAL_SYS/thermal_zone20/type"
rmdir "$MU300_THERMAL_SYS/thermal_zone20"
# Independent frequency and thermal saves, resets, persistence and boot replay.
freq='{"scope":"frequency","changes":[{"id":"policy0","cpus":"0 1 2 3","governor":"performance","min":100,"max":200}],"persist":true}'
printf '%s' "$freq" | call apply >/dev/null
test "$(cat "$z/trip_point_0_temp")" = 70000
printf '%s' "$payload" | call apply >/dev/null
test "$(cat "$p/scaling_max_freq")" = 200
test "$(cat "$p/scaling_governor")" = performance
out=$(call get)
test "$(check "$out" '@.persist')" = true
test "$(check "$out" '@.thermal_persist')" = true
thermal_profile=$(jsonfilter -i "$base/config.json" -e '@.thermal')
printf '{"scope":"frequency","reset":true}' | call apply >/dev/null
test "$(cat "$p/scaling_max_freq")" = 300
test "$(cat "$z/trip_point_0_temp")" = 69000
test "$(jsonfilter -i "$base/config.json" -e '@.thermal')" = "$thermal_profile"
test "$(check "$(call get)" '@.persist')" = false
printf '%s' "$freq" | call apply >/dev/null
frequency_profile=$(jsonfilter -i "$base/config.json" -e '@.frequency')
printf '{"scope":"thermal","reset":true}' | call apply >/dev/null
test "$(cat "$z/trip_point_0_temp")" = 70000
test "$(cat "$p/scaling_max_freq")" = 200
test "$(jsonfilter -i "$base/config.json" -e '@.frequency')" = "$frequency_profile"
test "$(check "$(call get)" '@.thermal_persist')" = false
printf '%s' "$payload" | call apply >/dev/null
# Cancelling one section's auto-apply preserves the other's profile and values.
printf '%s' "$payload" | sed 's/"persist":true/"persist":false/' | call apply >/dev/null
test "$(jsonfilter -i "$base/config.json" -e '@.frequency')" = "$frequency_profile"
test "$(cat "$z/trip_point_0_temp")" = 69000
printf '%s' "$payload" | call apply >/dev/null
# A stale combined UI is rejected before touching either domain or config.
before=$(cat "$base/config.json")
if printf '{"changes":[],"thermal":[],"persist":false}' | call apply >/dev/null; then exit 1; fi
test "$(cat "$base/config.json")" = "$before"
# Missing thermal capability must not block valid frequency startup settings.
printf 'disabled\n' > "$z/mode"
printf '300\n' > "$p/scaling_max_freq"
if call boot > "$base/result"; then exit 1; fi
test "$(cat "$p/scaling_max_freq")" = 200
test "$(jsonfilter -i "$base/result" -e '@.frequency.ok')" = 1
test "$(jsonfilter -i "$base/result" -e '@.thermal.ok')" = 0
test "$(cat "$base/config.json")" = "$before"
printf 'enabled\n' > "$z/mode"
# Invalid frequency profile must not prevent the valid thermal replay either.
ucode -e 'import * as fs from "fs"; let p=getenv("MU300_CPU_CONFIG"), c=json(fs.readfile(p)); c.frequency.changes[0].max=999; fs.writefile(p,sprintf("%J",c));'
printf '70000\n' > "$z/trip_point_0_temp"
printf '85000\n' > "$z/trip_point_1_temp"
if call boot > "$base/result"; then exit 1; fi
test "$(jsonfilter -i "$base/result" -e '@.frequency.ok')" = 0
test "$(jsonfilter -i "$base/result" -e '@.thermal.ok')" = 1
test "$(cat "$z/trip_point_0_temp")" = 69000
test "$(cat "$p/scaling_max_freq")" = 200
# Old combined profiles remain readable and replayable; first scoped save
# atomically migrates them without silently erasing the untouched half.
printf '%s\n' '{"version":1,"persist":true,"changes":[{"id":"policy0","cpus":"0 1 2 3","governor":"performance","min":100,"max":200}],"thermal":[{"zone":"soc-thmzone","trip":0,"temp":69000},{"zone":"soc-thmzone","trip":1,"temp":84000}]}' > "$base/config.json"
before=$(cat "$base/config.json")
call get >/dev/null
call boot >/dev/null
test "$(cat "$base/config.json")" = "$before"
printf '{"scope":"frequency","reset":true}' | call apply >/dev/null
test "$(jsonfilter -i "$base/config.json" -e '@.version')" = 2
test "$(check "$(call get)" '@.thermal_persist')" = true
test "$(cat "$z/trip_point_0_temp")" = 69000
printf '{"scope":"thermal","reset":true}' | call apply >/dev/null
test ! -e "$base/config.json"
test "$(cat "$p/scaling_max_freq")" = 300
test "$(cat "$z/trip_point_0_temp")" = 70000
echo 'PASS independent frequency/thermal save, reset, auto-apply, boot failure isolation, legacy migration and stale UI rejection'
echo 'PASS thermal discovery, limits, ordering, binding, persistence, boot, reset, rollback, read-only critical/hysteresis'
