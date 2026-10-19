#!/bin/sh
# Run in an OpenWrt container. /readonly is a read-only fixture bind mount,
# never host sysfs. All actual writes go to the container's temporary directory.
set -eu
lib=$1
base=$(mktemp -d)
trap 'rm -rf "$base"' EXIT
export UNISOC_CORES_SYS=$base/sys UNISOC_CORES_CONFIG=$base/profile.json
export UNISOC_CORES_DEFAULTS=$base/defaults.json UNISOC_CORES_ERROR=$base/error
mkdir -p "$UNISOC_CORES_SYS/cpu0" "$UNISOC_CORES_SYS/cpu1" "$UNISOC_CORES_SYS/cpu2" "$UNISOC_CORES_SYS/cpu3"
printf '1\n' > "$UNISOC_CORES_SYS/cpu1/online"
printf '1\n' > "$UNISOC_CORES_SYS/cpu2/online"
full='[{"id":0,"online":true},{"id":1,"online":true},{"id":2,"online":true},{"id":3,"online":true}]'
off='[{"id":0,"online":true},{"id":1,"online":false},{"id":2,"online":false},{"id":3,"online":true}]'
call() { ucode "$lib" "$@" > "$base/out"; }
request() { printf '{"cores":%s,"persist":%s}' "$1" "${2:-false}" | call apply; }
value() { jsonfilter -i "$base/out" -e "$1"; }
rejected() {
    if printf '%s' "$1" | call apply; then echo 'accepted invalid request'; exit 1; fi
    test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 1
    test "$(cat "$UNISOC_CORES_SYS/cpu2/online")" = 1
}
call get
test "$(value '@.cores[0].writable')" = false
test "$(value '@.cores[1].writable')" = true
test "$(value '@.cores[3].writable')" = false
test ! -e "$UNISOC_CORES_DEFAULTS"
call boot; test "$(value '@.skipped')" = true
test ! -e "$UNISOC_CORES_DEFAULTS"
request "$off"
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 0
test "$(cat "$UNISOC_CORES_SYS/cpu2/online")" = 0
test ! -e "$UNISOC_CORES_CONFIG"
request "$off"; request "$full"
# Authenticated HTTP ubus adds a session envelope; ignore only that metadata,
# never persist it, and keep rejecting unknown settings.
printf '{"cores":%s,"persist":true,"reset":false,"ubus_rpc_session":"0123456789abcdef0123456789abcdef"}' "$off" | call apply
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 0
! grep -q ubus_rpc_session "$UNISOC_CORES_CONFIG"
request "$full" false
rejected "$(printf '{"cores":%s,"persist":false,"ubus_rpc_session":"test","unknown":1}' "$full")"
for bad in \
 '{"cores":[{"id":0,"online":false},{"id":1,"online":false},{"id":2,"online":false},{"id":3,"online":true}],"persist":true}' \
 '{"cores":[{"id":0,"online":true},{"id":1,"online":false},{"id":1,"online":false},{"id":3,"online":true}],"persist":true}' \
 '{"cores":[{"id":0,"online":true},{"id":1,"online":false},{"id":2,"online":0},{"id":3,"online":true}],"persist":false}' \
 '{"cores":[{"id":0,"online":true},{"id":1,"online":false},{"id":2,"online":false},{"id":3,"online":false}],"persist":false}' \
 '{"cores":[{"id":0,"online":true},{"id":"../../etc/passwd","online":false},{"id":2,"online":false},{"id":3,"online":true}],"persist":false}' \
 '{"cores":[{"id":0,"online":true}],"persist":false}' \
 '{"cores":[],"persist":"yes"}' \
 '{"cores":[],"persist":false,"unknown":1}'; do rejected "$bad"; done
# Persistent replay, no rewriting of the profile at each boot, and opt-out.
request "$off" true
cp "$UNISOC_CORES_CONFIG" "$base/saved"
printf '1\n' > "$UNISOC_CORES_SYS/cpu1/online"
printf '1\n' > "$UNISOC_CORES_SYS/cpu2/online"
call boot
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 0
cmp "$base/saved" "$UNISOC_CORES_CONFIG"
printf '{"reset":true,"persist":false}' | call apply
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 1
test "$(cat "$UNISOC_CORES_SYS/cpu2/online")" = 1
test ! -e "$UNISOC_CORES_CONFIG"
# A genuine read-only filesystem rejects the second core after the first
# changed successfully. Both must return to the original online state.
rm "$UNISOC_CORES_SYS/cpu2/online"
ln -s /readonly/online "$UNISOC_CORES_SYS/cpu2/online"
if request "$off" true; then echo 'readonly hotplug write accepted'; exit 1; fi
test "$(value '@.error')" = cpu_cores_write
test "$(value '@.rollback')" = true
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 1
test "$(cat "$UNISOC_CORES_SYS/cpu2/online")" = 1
test ! -e "$UNISOC_CORES_CONFIG"
rm "$UNISOC_CORES_SYS/cpu2/online"
printf '1\n' > "$UNISOC_CORES_SYS/cpu2/online"
# Failed persistence also restores runtime state and keeps prior disk data.
original=$UNISOC_CORES_CONFIG
export UNISOC_CORES_CONFIG=/readonly/profile.json
if request "$off" true; then echo 'readonly persistence accepted'; exit 1; fi
test "$(value '@.error')" = cpu_cores_save
test "$(value '@.rollback')" = true
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 1
test "$(cat "$UNISOC_CORES_SYS/cpu2/online")" = 1
export UNISOC_CORES_CONFIG=$original
printf '{"version":1,"cores":[{"id":99,"online":false}]}' > "$UNISOC_CORES_CONFIG"
if call boot; then echo 'stale boot profile accepted'; exit 1; fi
test "$(cat "$UNISOC_CORES_SYS/cpu1/online")" = 1
test -s "$UNISOC_CORES_ERROR"
request "$full" false
test ! -e "$UNISOC_CORES_CONFIG"
test ! -e "$UNISOC_CORES_ERROR"
# Ignore possible-but-absent cores; accept sparse present CPU ranges.
printf '0-1,3\n' > "$UNISOC_CORES_SYS/present"
call get
test "$(value '@.cores[2].id')" = 3
test -z "$(value '@.cores[3].id')"
echo 'PASS core discovery, validation, fixed cores, temporary/persistent settings, boot replay, reset, write/save rollback'
