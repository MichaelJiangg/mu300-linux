import * as policy from '../openwrt/overlay/opt/mu300/lib/network-recovery.uc';
let count = 0;
function check(test, name) {
    if (!test) die('FAIL: ' + name + '\n');
    count++;
}
function status() {
    return { proto: 'mu300cell', autostart: true, up: false, pending: false,
        available: false, errors: [{ code: 'REGISTRATION_WAIT' }] };
}
let s = status(), notifications = 0;
check(!policy.radio_blocked(true, true), 'native RF ready despite persistent legacy freeze');
check(policy.radio_blocked(true, false), 'native cold-start not ready');
check(!policy.radio_blocked(false, false), 'legacy radio path unchanged');
function call(method, payload) {
    if (method == 'status') return s;
    check(payload.action == 5 && payload.available === true, 'only restore availability');
    notifications++;
    return {};
}
let previous = { key: null, attempted: false };
let registered = { slot: 1, stat: 1, rat: 7 };
check(policy.recovery(call, registered, 1, 1, false, previous), 'registered slot resumes');
check(!policy.recovery(call, registered, 1, 1, false, previous), 'netifd echo does not loop');
check(notifications == 1, 'one notification per transition');
for (let stat in [0, 2, 3, 4, 6, 7, 8, 9, 10])
    check(policy.registration_key({slot: 1, stat, rat: 7}, 1) == null, 'non PS state ' + stat);
check(policy.registration_key({slot: 0, stat: 1, rat: 7}, 1) == null, 'other SIM ignored');
check(policy.registration_key({slot: 1, stat: 5, rat: null}, 1) != null, 'EPS roaming without optional RAT');
check(policy.registration_key({slot: 1, stat: 1, rat: 255}, 1) == null, 'invalid RAT');
for (let field in ['autostart', 'available', 'pending', 'up', 'proto']) {
    let broken = status();
    broken[field] = field == 'proto' ? 'static' : field == 'autostart' ? false : true;
    check(!policy.can_resume(broken, 1, 1, false), 'preserve ' + field);
}
check(!policy.can_resume(status(), 0, 1, false), 'old SIM wait ignored');
check(!policy.can_resume(status(), null, 1, false), 'no registration wait');
check(!policy.can_resume(status(), 1, 1, true), 'manual down or switching blocked');
s = status(); s.errors = [{code:'NO_MODEM'}];
check(!policy.can_resume(s, 1, 1, false), 'fatal error not bypassed');
policy.recovery(call, {slot:1,stat:2,rat:7}, 1, 1, false, previous);
s = status();
check(policy.recovery(call, registered, 1, 1, false, previous), 'next registration resumes');
printf('PASS: %d recovery policy checks\n', count);
