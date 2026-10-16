#!/bin/sh
# Isolated fake sysfs and firmware gate. Never loads a module or adjusts voltage.
set -eu
lib=$1
base=$(mktemp -d /tmp/mu300-voltage-test.XXXXXX)
export MU300_CPU_VOLTAGE_DIR=$base/etc MU300_CPU_VOLTAGE_RUN=$base/run
export MU300_CPU_SYS=$base/sys MU300_CPU_BOOT_ID=$base/boot
export MU300_CPU_PLATFORM=$base/platform
mkdir -p "$base/etc" "$base/run" "$base/sys"
printf 'boot-one\n' > "$base/boot"
printf '#!/bin/sh\ntest ! -f "%s/unsupported"\n' "$base" > "$base/platform"
chmod 755 "$base/platform"
for d in 0 1 2; do
    dir=$base/sys/policy$d; mkdir -p "$dir"
    printf '%s\n' "$d" > "$dir/scaling_voltage_domain"
    printf '0\n' > "$dir/scaling_voltage_offset"
    printf '%s\n' "$d" > "$dir/affected_cpus"
    printf '1000000 750000\n1500000 850000\n' > "$dir/scaling_voltage_table"
done
call() { ucode "$lib" "$@"; }
check() { jsonfilter -s "$1" -e "$2"; }
out=$(call get)
test "$(check "$out" '@.supported')" = true
test "$(check "$out" '@.domains[0].table[0].uv')" = 750000
for bad in '[]' '[1,0,0]' '[-53125,0,0]' '[28125,0,0]' '[0,0]' '["0",0,0]' '[0,0,0,0]' '[true,0,0]' '[0.5,0,0]'; do
    if printf '{"offsets":%s}' "$bad" | call save > "$base/out"; then echo 'accepted invalid offsets'; exit 1; fi
done
test ! -e "$base/etc/cpu-voltage.json"
out=$(printf '{"offsets":[-3125,0,6250]}' | call save)
test "$(check "$out" '@.pending')" = true
test "$(call boot-args)" = '-3125,0,6250'
test -f "$base/etc/cpu-voltage-armed.json"
# Repeating startup cannot apply an offset twice.
test "$(call boot-args)" = '0,0,0'
# Reset while running must not erase the crash guard.
printf '{"offsets":[0,0,0]}' | call save > "$base/out"
test -f "$base/etc/cpu-voltage-armed.json"
call shutdown > "$base/out"
test ! -e "$base/etc/cpu-voltage-armed.json"
printf '{"offsets":[-3125,0,0]}' | call save > "$base/out"
test "$(call boot-args)" = '-3125,0,0'
# Simulate an unclean boot, reject persisted voltage and never retry it.
printf 'boot-two\n' > "$base/boot"
test "$(call boot-args)" = '0,0,0'
test -f "$base/etc/cpu-voltage.json.rejected"
test ! -e "$base/etc/cpu-voltage.json"
out=$(call get)
test "$(check "$out" '@.recovery')" = unclean_shutdown
# A clean shutdown preserves a saved profile across boots.
printf '{"offsets":[0,3125,0]}' | call save > "$base/out"
test "$(call boot-args)" = '0,3125,0'
call shutdown > "$base/out"
printf 'boot-three\n' > "$base/boot"
test "$(call boot-args)" = '0,3125,0'
call shutdown > "$base/out"
# Unknown firmware may reset to defaults, but may not save/apply an offset.
touch "$base/unsupported"
if printf '{"offsets":[-3125,0,0]}' | call save > "$base/out"; then exit 1; fi
test "$(call boot-args)" = '0,0,0'
printf '{"offsets":[0,0,0]}' | call save > "$base/out"
# Missing/duplicate domain interfaces are unsupported, never fabricate controls.
rm "$base/unsupported" "$base/sys/policy2/scaling_voltage_domain"
if printf '{"offsets":[0,0,3125]}' | call save > "$base/out"; then exit 1; fi
test ! -e "$base/etc/cpu-voltage-armed.json"
echo "PASS voltage validation/gate/persistence/reset/clean+unclean recovery: $base"
