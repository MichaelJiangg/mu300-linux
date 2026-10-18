import * as fs from 'fs';
import { run_guard } from '/guard/events.uc';

const board = ARGV[0] == 'uvlo' ? {
    uvlo: { shutdown_uv: 3100000, offset_uv: 120000, check_below_uv: 3400000,
            interval_ms: 800, samples: 5 },
} : {};
function increment(name) {
    fs.writefile('/fixtures/' + name, '' + (int(fs.readfile('/fixtures/' + name) ?? '0') + 1));
}
run_guard(board, () => {
    increment('reads');
    return json(fs.readfile('/fixtures/state.json'));
}, reason => {
    increment('offcount');
    fs.writefile('/fixtures/reason', reason);
});
