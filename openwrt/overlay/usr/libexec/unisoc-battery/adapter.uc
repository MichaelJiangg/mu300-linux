import * as fs from 'fs';
import { snapshot, text } from './read.uc';

export function profile(root) {
    root = root ?? '';
    // F50/V50 have no battery: never infer presence from their synthetic FGU.
    if (text(root + '/run/mu300/device') != 'u30air') return null;
    const raw = fs.readfile(root + '/sys/firmware/devicetree/base/charger-manager/cm-shutdown-voltage');
    let voltage = null;
    if (raw != null && length(raw) == 4)
        voltage = ord(raw, 0) * 16777216 + ord(raw, 1) * 65536 + ord(raw, 2) * 256 + ord(raw, 3);
    if (!(voltage > 0)) die('battery-guard: U30 Air stock shutdown voltage is missing\n');
    // The first hardware alarm uses the battery design minimum (3.45 V on
    // stock U30 Air), above the stock 3.40 V recheck gate. Keep watching that
    // alarm band until voltage recovers, without changing shutdown thresholds.
    const alarm = fs.readfile(root + '/sys/firmware/devicetree/base/battery/voltage-min-design-microvolt');
    let alarm_uv = 3400000;
    if (alarm != null && length(alarm) == 4) {
        const value = ord(alarm, 0) * 16777216 + ord(alarm, 1) * 65536 + ord(alarm, 2) * 256 + ord(alarm, 3);
        if (value > alarm_uv) alarm_uv = value;
    }
    // Stock 5.4.254 cm_uvlo_check_work: 5 samples, 200 jiffies at HZ=250.
    return { uvlo: { shutdown_uv: voltage, offset_uv: 120000,
                     check_below_uv: alarm_uv, interval_ms: 800, samples: 5 } };
};

export function sample(root) {
    root = root ?? '/sys/class/power_supply';
    return snapshot(root, ['sc27xx-fgu', 'battery']);
};
