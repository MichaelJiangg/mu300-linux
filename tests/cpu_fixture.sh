#!/bin/sh
# Works with OpenWrt ucode on the device or in the build image, never real sysfs.
set -eu
lib=$1
base=$(mktemp -d /tmp/mu300-cpu-test.XXXXXX)
export MU300_CPU_SYS=$base/sys MU300_CPU_CONFIG=$base/cpu.json
export MU300_THERMAL_SYS=$base/thermal MU300_CPU_DEFAULTS=$base/defaults.json MU300_CPU_BOOT_ID=$base/boot
mkdir -p "$MU300_CPU_SYS/policy0" "$MU300_CPU_SYS/policy4" "$MU300_THERMAL_SYS"
printf 'cpu-fixture-boot\n' > "$base/boot"
for id in policy0 policy4; do
    d=$MU300_CPU_SYS/$id
    printf '0 1\n' > "$d/affected_cpus"
    printf 'test-driver\n' > "$d/scaling_driver"
    printf 'schedutil performance\n' > "$d/scaling_available_governors"
    printf 'schedutil\n' > "$d/scaling_governor"
    printf '100 200 300\n' > "$d/scaling_available_frequencies"
    printf '100\n' > "$d/cpuinfo_min_freq"; printf '300\n' > "$d/cpuinfo_max_freq"
    printf '100\n' > "$d/scaling_min_freq"; printf '300\n' > "$d/scaling_max_freq"
done
call() { ucode "$lib" "$@"; }
request='{"persist":true,"changes":[{"id":"policy0","cpus":"0 1","governor":"performance","min":200,"max":300}]}'
printf '%s' "$request" | call apply > "$base/out"
test "$(cat "$MU300_CPU_SYS/policy0/scaling_min_freq")" = 200
test -f "$MU300_CPU_CONFIG"
printf '100\n' > "$MU300_CPU_SYS/policy0/scaling_min_freq"
call boot > "$base/out"
test "$(cat "$MU300_CPU_SYS/policy0/scaling_min_freq")" = 200
# Out-of-range, unavailable frequency, wrong topology and traversal never write.
for request in \
'{"persist":false,"changes":[{"id":"policy0","cpus":"0 1","governor":"performance","min":400,"max":500}]}' \
'{"persist":false,"changes":[{"id":"policy0","cpus":"0 1","governor":"performance","min":150,"max":300}]}' \
'{"persist":false,"changes":[{"id":"policy0","cpus":"7","governor":"performance","min":100,"max":300}]}' \
'{"persist":false,"changes":[{"id":"../policy0","cpus":"0 1","governor":"performance","min":100,"max":300}]}'; do
    if printf '%s' "$request" | call apply > "$base/out"; then echo 'invalid request accepted'; exit 1; fi
    test "$(cat "$MU300_CPU_SYS/policy0/scaling_min_freq")" = 200
    test -f "$MU300_CPU_CONFIG"
done
# A persistence failure rolls back all successfully changed policy values.
old=$MU300_CPU_CONFIG; export MU300_CPU_CONFIG=$base/missing/config
if printf '%s' '{"persist":true,"changes":[{"id":"policy0","cpus":"0 1","governor":"schedutil","min":100,"max":200}]}' | call apply > "$base/out"; then exit 1; fi
test "$(cat "$MU300_CPU_SYS/policy0/scaling_min_freq")" = 200
test "$(cat "$MU300_CPU_SYS/policy0/scaling_max_freq")" = 300
test "$(cat "$MU300_CPU_SYS/policy0/scaling_governor")" = performance
export MU300_CPU_CONFIG=$old
printf '%s' '{"persist":false,"changes":[{"id":"policy0","cpus":"0 1","governor":"schedutil","min":100,"max":300}]}' | call apply > "$base/out"
test ! -e "$MU300_CPU_CONFIG"
call boot > "$base/out"
echo "PASS CPU validation/persistence/restore/rollback/temporary: $base"
