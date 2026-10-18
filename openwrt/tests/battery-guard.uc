// Run with the actual firmware ucode runtime; every poweroff is a mock.
import * as fs from 'fs';
import { assess } from '/guard/policy.uc';
import { create_guard } from '/guard/guard.uc';
import { snapshot } from '/guard/read.uc';

let checks = 0;
function check(value, name) {
    if (!value) die('FAIL: ' + name + '\n');
    checks++;
}
function sample(extra) {
    const result = { present: 1, capacity: 40, level_supported: false, status: 'Discharging', voltage: 3800000 };
    for (let key in keys(extra ?? {})) result[key] = extra[key];
    return result;
}
function reason(s) { return assess(s, {}, { count: 0 }, false).reason; }

check(reason(sample({ level_supported: true, level: 'Critical', capacity: 20, status: 'Charging' })) == 'critical', 'HAL critical owns charging exception');
for (let level in ['Low', 'Normal', 'High', 'Full', 'Unknown', null, '', 'garbage'])
    check(!reason(sample({ level_supported: true, level, capacity: 0 })), 'supported noncritical or unreadable level: ' + level);
for (let status in ['Discharging', 'Not charging', 'Full', 'Unknown'])
    check(reason(sample({ capacity: 0, status })) == 'empty', 'unsupported level empty: ' + status);
check(!reason(sample({ capacity: 0, status: 'Charging' })), 'empty while charging');
check(!reason(sample({ capacity: 0, status: null })), 'status read failure');
check(!reason(sample({ capacity: null })), 'capacity read failure');
check(!reason(sample({ capacity: 1 })), 'one percent alone is not a shutdown threshold');
for (let present in [0, null])
    check(!reason(sample({ present, level_supported: true, level: 'Critical' })), 'absent or unreadable presence');

const board = { uvlo: { shutdown_uv: 3100000, offset_uv: 120000,
                       check_below_uv: 3400000, interval_ms: 800, samples: 5 } };
let current = sample(), requests = [], delays = [], cancels = 0;
function make_guard() {
    return create_guard(board, {
        read: () => current,
        poweroff: why => push(requests, why),
        schedule: ms => push(delays, ms),
        cancel: () => cancels++,
    });
}
let guard = make_guard();
guard.event();
check(length(delays) == 0 && length(requests) == 0, 'normal voltage idle without timer');
current = sample({ capacity: 1, voltage: 3220000 });
guard.event();
check(length(delays) == 1 && delays[0] == 800, 'stock UVLO interval');
for (let i = 0; i < 100; i++) guard.event();
check(length(delays) == 1 && length(requests) == 0, 'event burst neither advances samples nor postpones timer');
for (let i = 0; i < 3; i++) guard.tick();
check(length(requests) == 0, 'four low samples cannot shut down');
guard.tick();
check(length(requests) == 1 && requests[0] == 'undervoltage', 'fifth low sample plus rounded one percent');
for (let i = 0; i < 10; i++) { guard.tick(); guard.event(); }
check(length(requests) == 1, 'only one poweroff per accepted shutdown');

requests = []; delays = []; cancels = 0;
guard = make_guard(); current = sample({ capacity: 20, voltage: 3200000 });
guard.event();
for (let i = 0; i < 8; i++) guard.tick();
check(length(requests) == 0, 'low voltage above final threshold with SOC above one');
current.voltage = 3100000; guard.tick();
check(length(requests) == 1, 'final undervoltage independent of a wrong high SOC');

requests = []; delays = []; cancels = 0;
guard = make_guard(); current = sample({ capacity: 1, voltage: 3200000 });
guard.event(); guard.tick();
current.voltage = null; guard.tick(); guard.tick();
check(length(requests) == 0, 'I/O errors never count as low samples');
current.voltage = 3300000; guard.tick(); // within alarm band but above count threshold
current.voltage = 3200000;
for (let i = 0; i < 4; i++) guard.tick();
check(length(requests) == 0, 'voltage recovery resets consecutive count');
current.voltage = 3400000; guard.event();
check(cancels == 1, 'leaving low-voltage band disarms timer');
current = sample({ capacity: 0, status: 'Charging' });
guard.event();
check(length(requests) == 0, 'charging at boot is not the unsupported-level empty case');
current.status = 'Not charging'; guard.event(); guard.event();
check(length(requests) == 1 && requests[0] == 'empty', 'charger-online pause does not hide an empty discharging battery');

const alarm_board = { uvlo: { shutdown_uv: 3100000, offset_uv: 120000,
                             check_below_uv: 3450000, interval_ms: 800, samples: 5 } };
const alarm_state = { count: 0, active: false };
let alarm = assess(sample({ capacity: 20, voltage: 3440000 }), alarm_board, alarm_state, false);
check(alarm.next == 800 && !alarm.reason && alarm_state.count == 0, 'first DT voltage alarm arms monitoring without changing shutdown threshold');
for (let i = 0; i < 5; i++)
    alarm = assess(sample({ capacity: 20, voltage: 3100000 }), alarm_board, alarm_state, true);
check(alarm.reason == 'undervoltage', 'continued voltage dip is caught without requiring a second hardware alarm');

// Real sysfs-like input parser: no missing read may turn into 0 percent.
const root = '/fixtures', path = root + '/battery';
function put(name, value) { fs.writefile(path + '/' + name, value); }
put('type', 'Battery\n'); put('present', '1\n'); put('capacity', '0\n');
put('status', 'Discharging\n'); put('voltage_now', '3100000\n');
check(reason(snapshot(root, ['battery'])) == 'empty', 'real parser reads zero capacity');
for (let value in ['', 'error', '-1', '101', '1.5']) {
    put('capacity', value);
    check(!reason(snapshot(root, ['battery'])), 'invalid capacity is not empty: ' + value);
}
put('capacity', '0\n'); fs.unlink(path + '/status');
check(!reason(snapshot(root, ['battery'])), 'missing status file');
put('status', 'Charging\n');
check(!reason(snapshot(root, ['battery'])), 'real parser charging');
put('status', 'Discharging\n'); put('capacity_level', 'Low\n');
check(!reason(snapshot(root, ['battery'])), 'supported capacity level takes precedence');
put('capacity_level', 'Critical\n');
check(reason(snapshot(root, ['battery'])) == 'critical', 'real parser critical');
put('present', '0\n');
check(!reason(snapshot(root, ['battery'])), 'physical battery removed');
print('PASS: ' + checks + ' native ucode low-battery checks; all poweroffs mocked\n');
