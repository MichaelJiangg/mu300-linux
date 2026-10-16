// Active policy only: power events plus a low-frequency SOC check.
// This FGU has no periodic percentage uevents; sysfs inotify is not reliable.
import * as fs from 'fs';
import * as ubus from 'ubus';
import * as uloop from 'uloop';

uloop.init();
const bus = ubus.connect(null, 2);
if (!bus) die('Charge policy: ubus unavailable\n');
let pending = false;
let check;
check = uloop.timer(-1, () => {
    pending = false;
    let pipe = fs.popen('/usr/libexec/unisoc-modem/charge apply', 'r');
    let state;
    if (pipe) {
        try { state = json(pipe.read('all')); } catch (e) {}
        pipe.close();
    }
    // A completed one-off charge needs no further SOC timer. A later power
    // event can still be handled while this loop is blocked in epoll.
    if (!state?.ok || (!state.paused && (state.enabled || state.full_once))) check.set(30000);
});
const event = bus.listener('mu300.charge', () => {
    if (!pending) { pending = true; check.set(100); }
});
if (!event) die('Charge policy: event subscription failed\n');
const term = uloop.signal(15, () => uloop.end());
const interrupt = uloop.signal(2, () => uloop.end());
check.set(30000);
uloop.run();
