# Sourced once by RPC workers. Never changes the modem's data SIM.
sim_scope() {
    case "$1" in 0|1) ;; *) return 1 ;; esac
    # A detached job inherits its parent's scoped paths; never suffix twice.
    if [ -n "${MU300_SCOPED_SLOT:-}" ]; then
        [ "$MU300_SCOPED_SLOT" = "$1" ]; return
    fi
    export MU300_SIM_SLOT=$1
    if [ "$1" = 1 ]; then
        [ "$(uci -q get unisoc_modem.main.sim_slots)" = 2 ] || return 1
    fi
    export MU300_SCOPED_SLOT=$1
    [ "$1" = 1 ] || return 0
    export MU300_DASH_DIR=${MU300_DASH_DIR:-/tmp/unisoc-modem}/sim1
    export MU300_STATE_DIR=${MU300_STATE_DIR:-$(uci -q get unisoc_modem.main.state_dir)}
    export MU300_STATE_DIR=${MU300_STATE_DIR:-/etc/unisoc-modem/lock-state.d}/sim1
    export MU300_DASH_IDENT_DIR=$MU300_STATE_DIR/identity
    # The MU300 platform's dedicated slot-1 reader; custom backends receive
    # MU300_SIM_SLOT and must provide the same per-request addressing guarantee.
    export MU300_AT_DIR=/run/mu300-at4
    export MU300_DASH_AT_DIR=/run/mu300-at4
    export UNISOC_REPLAY_MARKER=/run/unisoc-modem-lock-replay-done-sim1
}
