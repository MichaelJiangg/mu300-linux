# Sourced by lock. Transient job results stay in RAM; polling sends no AT.
JOBROOT=$RUNDIR/lock-jobs
job_uptime() { local n rest; read -r n rest < /proc/uptime; printf '%s' "${n%%.*}"; }
job_path() {
    printf '%s\n' "$1" | grep -Eq '^[A-Za-z0-9]{10}$' || return 1
    JOBDIR=$JOBROOT/$1
    [ -d "$JOBDIR" ]
}
job_write() {
    printf '{"id":"%s","state":"%s","ok":%s,"error":%s}\n' \
        "${JOBDIR##*/}" "$1" "$2" "$(qs "$3")" > "$JOBDIR/result.$$" &&
        mv "$JOBDIR/result.$$" "$JOBDIR/result"
}
job_status() {
    local age started pid
    job_path "$1" || { printf '{"ok":0,"state":"error","error":"操作结果已过期或不存在"}\n'; return; }
    if ! grep -Eq '"state":"(done|error)"' "$JOBDIR/result"; then
        started=$(cat "$JOBDIR/started"); age=$(( $(job_uptime) - started ))
        pid=$(cat "$JOBDIR/pid" 2>/dev/null)
        if [ "$age" -gt "${MU300_JOB_TIMEOUT:-240}" ]; then
            job_write error 0 '应用超时，请刷新确认模组状态'
        elif [ "$age" -gt 2 ] && { [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; }; then
            job_write error 0 '设置进程已中断，请刷新确认模组状态'
        fi
    fi
    cat "$JOBDIR/result"
}
job_start() {
    local d n=0 active=0 id age
    validate_apply "$1" "$2" 2>/dev/null || {
        printf '{"ok":0,"error":%s}\n' "$(qs "$(validate_apply "$1" "$2" 2>&1)")"; return;
    }
    umask 077
    mkdir -p "$JOBROOT" || return 1
    # Bound memory and background work. No permanent polling daemon, no flash
    # writes per status query. Submission is fail-fast when already contended.
    mkdir "$JOBROOT/submit" 2>/dev/null || {
        printf '{"ok":0,"error":"另一项网络设置仍在执行，请稍后重试"}\n'; return;
    }
    trap 'rmdir "$JOBROOT/submit" 2>/dev/null' EXIT
    for d in "$JOBROOT"/??????????; do
        [ -d "$d" ] || continue
        job_status "${d##*/}" >/dev/null
        age=$(( $(job_uptime) - $(cat "$d/started") ))
        if grep -Eq '"state":"(done|error)"' "$d/result"; then
            # Exact generated ten-character child directories only.
            if [ "$age" -gt 600 ] && ! kill -0 "$(cat "$d/pid" 2>/dev/null)" 2>/dev/null; then
                rm -f "$d"/result "$d"/started "$d"/pid "$d"/error
                rmdir "$d" 2>/dev/null || true
                continue
            fi
        else
            active=$((active + 1))
        fi
        n=$((n + 1))
    done
    [ "$active" -lt 4 ] && [ "$n" -lt 64 ] || { printf '{"ok":0,"error":"另一项网络设置仍在执行，请稍后重试"}\n'; return; }
    JOBDIR=$(mktemp -d "$JOBROOT/XXXXXXXXXX") || return 1
    id=${JOBDIR##*/}
    job_uptime > "$JOBDIR/started"
    job_write queued 0 '' || return 1
    setsid "$0" worker "$id" "$1" "$2" </dev/null >/dev/null 2>&1 &
    printf '{"ok":1,"started":1,"id":"%s","kind":"%s"}\n' "$id" "$1"
}
job_worker() {
    local rc error
    job_path "$1" || return 1
    echo $$ > "$JOBDIR/pid"
    job_write running 0 '' || return 1
    # The child owns/releases the modem mutex. Exit status and fresh modem
    # verification, never cached timestamps, determine this job's result.
    "$0" apply "$2" "$3" >/dev/null 2> "$JOBDIR/error"
    rc=$?
    if [ $(( $(job_uptime) - $(cat "$JOBDIR/started") )) -gt "${MU300_JOB_TIMEOUT:-240}" ]; then
        job_write error 0 '应用超时，请刷新确认模组状态'
    elif [ "$rc" = 0 ]; then
        job_write done 1 ''
    else
        error=$(tail -c 512 "$JOBDIR/error")
        job_write error 0 "${error:-网络设置执行失败}"
    fi
}
