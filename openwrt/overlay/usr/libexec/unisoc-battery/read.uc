import * as fs from 'fs';

export function text(path) {
    const value = fs.readfile(path);
    return value == null ? null : trim(value);
};

export function number(path, maximum) {
    const value = text(path);
    if (value == null || !match(value, /^(0|[1-9][0-9]*)$/)) return null;
    const result = int(value);
    return result >= 0 && (maximum == null || result <= maximum) ? result : null;
};

export function snapshot(root, names) {
    for (let name in names) {
        const path = root + '/' + name;
        if (text(path + '/type') != 'Battery') continue;
        const status = text(path + '/status');
        return {
            present: number(path + '/present', 1),
            capacity: number(path + '/capacity', 100),
            level_supported: fs.stat(path + '/capacity_level') != null,
            level: text(path + '/capacity_level'),
            status: index(['Unknown', 'Charging', 'Discharging', 'Not charging', 'Full'], status) >= 0 ? status : null,
            voltage: number(path + '/voltage_now'),
        };
    }
    return null;
};
