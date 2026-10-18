import * as fs from 'fs';
import { profile } from '/guard/adapter.uc';

let checks = 0;
function check(value, name) {
    if (!value) die('FAIL: ' + name + '\n');
    checks++;
}
const root = '/fixtures';
if (ARGV[0] == 'e5') {
    check(profile(root) == null, 'no board profile');
    for (let model in ['e5', 't551m', 'm8']) {
        fs.writefile(root + '/etc/e5/device-profile', model + '\n');
        const board = profile(root);
        check(board != null && !board.uvlo, 'kernel keeps existing voltage policy: ' + model);
    }
}
else {
    for (let model in ['f50', 'v50', 'mu300', '', 'unknown']) {
        fs.writefile(root + '/run/mu300/device', model + '\n');
        check(profile(root) == null, 'batteryless or unadapted board: ' + model);
    }
    fs.writefile(root + '/run/mu300/device', 'u30air\n');
    const path = root + '/sys/firmware/devicetree/base/charger-manager/cm-shutdown-voltage';
    fs.writefile(path, chr(0) + chr(0x2f) + chr(0x4d) + chr(0x60));
    const board = profile(root);
    check(board.uvlo.shutdown_uv === 3100000, 'stock big-endian DT shutdown voltage');
    check(board.uvlo.interval_ms === 800 && board.uvlo.samples === 5 &&
          board.uvlo.offset_uv === 120000 && board.uvlo.check_below_uv === 3400000,
          'stock U30 UVLO qualification');
    const alarm = root + '/sys/firmware/devicetree/base/battery/voltage-min-design-microvolt';
    fs.writefile(alarm, chr(0) + chr(0x34) + chr(0xa4) + chr(0x90));
    check(profile(root).uvlo.check_below_uv === 3450000, 'DT hardware alarm arms UVLO before a later voltage dip');
    fs.writefile(path, 'bad');
    let rejected = false;
    try { profile(root); } catch (e) { rejected = true; }
    check(rejected, 'malformed DT cannot become an invented threshold');
}
print('PASS: ' + checks + ' board adapter checks\n');
