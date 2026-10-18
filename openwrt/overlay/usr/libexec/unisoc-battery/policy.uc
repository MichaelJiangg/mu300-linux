// Android BatteryService semantics; board-specific UVLO comes from the adapter.
export function assess(sample, profile, state, tick) {
    if (!sample || sample.present !== 1) {
        state.active = false;
        state.count = 0;
        return {};
    }

    if (sample.level_supported) {
        if (sample.level == 'Critical') return { reason: 'critical' };
    }
    else if (sample.capacity === 0 && sample.status != null && sample.status != 'Charging') {
        return { reason: 'empty' };
    }

    const uvlo = profile.uvlo;
    if (!uvlo) return {};
    if (sample.voltage == null || sample.capacity == null) {
        // A failed read is not a new low-voltage sample.
        return state.active ? { next: uvlo.interval_ms } : {};
    }
    if (sample.voltage >= uvlo.check_below_uv) {
        state.active = false;
        state.count = 0;
        return {};
    }
    if (sample.voltage > uvlo.shutdown_uv + uvlo.offset_uv)
        state.count = 0;
    else if (tick || !state.active)
        state.count++;
    state.active = true;

    if (state.count >= uvlo.samples && (sample.capacity <= 1 || sample.voltage <= uvlo.shutdown_uv))
        return { reason: 'undervoltage' };
    return { next: uvlo.interval_ms };
};
