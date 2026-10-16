#!/bin/sh
# One bounded installer stage, in its own process group. Never wait for a
# timed-out kernel I/O request, never retry it, and never run sync on failure.
set -u
BB=${MU300_BUSYBOX:?}
if [ "${1:-}" = --worker ]; then
    result=$2; shift 2
    "$@"
    rc=$?
    printf '%s\n' "$rc" > "$result.tmp"
    mv "$result.tmp" "$result"
    exit "$rc"
fi
name=$1; limit=$2; shift 2
state=${MU300_TF_STATE:?}
job=$(mktemp -d "$state/$name.XXXXXX") || exit 1
msg() { if [ "${MU300_INSTALL_LANG:-en}" = zh ]; then echo "$1"; else echo "$2"; fi; }
case $name in
    preflight) zh_name=安装包与容量校验 ;;
    vendor-preflight) zh_name=设备固件预检与暂存 ;;
    staging-space) zh_name=剩余空间检查 ;;
    rootfs) zh_name=TF文件系统安装与回读 ;;
    boot-write) zh_name=写入启动镜像 ;;
    boot-readback) zh_name=启动镜像回读校验 ;;
    arm-slot) zh_name=设置启动槽位 ;;
    *) zh_name=$name ;;
esac
msg "[TF] 阶段：$zh_name（上限 ${limit} 秒）" "[TF] stage: $name (limit ${limit}s)"
"$BB" setsid "$BB" sh "$0" --worker "$job/result" "$@" > "$job/output.log" 2>&1 &
pid=$!
start=$(cut -d. -f1 /proc/uptime)
last=$start; previous=; shown=0
stop_worker() {
    # Only this stage's session, not Magisk or another installer.
    "$BB" kill -TERM -- "-$pid" 2>/dev/null || true
    "$BB" kill -KILL -- "-$pid" 2>/dev/null || true
}
trap 'stop_worker; exit 130' INT TERM HUP
while :; do
    size=$(wc -c < "$job/output.log")
    if [ "$size" -gt "$shown" ]; then
        tail -c +$((shown + 1)) "$job/output.log"
        shown=$size
    fi
    if [ -f "$job/result" ]; then
        # The worker can finish between the size sample and this check.
        tail -c +$((shown + 1)) "$job/output.log"
        rc=$(cat "$job/result")
        wait "$pid" 2>/dev/null || true
        case $rc in 0) exit 0 ;; *) exit 1 ;; esac
    fi
    now=$(cut -d. -f1 /proc/uptime)
    # Block completion counters, not log heartbeats, identify actual I/O
    # progress. Total deadline still applies if a broken driver spins/retries.
    progress=$(cat /sys/class/block/mmcblk1/stat 2>/dev/null):$size
    if [ "$progress" != "$previous" ]; then last=$now; previous=$progress; fi
    if [ $((now - start)) -ge "$limit" ] || [ $((now - last)) -ge 120 ]; then
        stop_worker
        : > "$state/reboot-required"
        msg "[TF] $zh_name 超时，已停止后续写入。请重启 Android 后重试；内核阻塞的 I/O 可能无法被终止。日志：$job" \
            "[TF] $name timed out; no further writes. Reboot Android before retrying: kernel-blocked I/O may not be killable. Log: $job"
        exit 124
    fi
    [ $(( (now - start) % 10 )) -ne 0 ] || msg "[TF] $zh_name：已运行 $((now - start)) 秒" "[TF] $name: $((now - start))s elapsed"
    sleep 2
done
