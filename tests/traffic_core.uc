// Run: TZ=UTC0 ucode -L openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem tests/traffic_core.uc
import * as c from 'traffic-core';
let checks = 0;
function check(value, label) { if (!value) die('FAIL: ' + label + '\n'); checks++; }
function stamp(y, m, d, h, min, sec) {
    return timelocal({ year:y, mon:m, mday:d, hour:h ?? 0, min:min ?? 0, sec:sec ?? 0, isdst:-1 });
}
function sample(rx, tx, boot, idx) { return { rx:rx, tx:tx, boot:boot || 'A', ifindex:idx || 3, device:'cell0' }; }
let now = stamp(2026, 10, 7), db = c.fresh(now);
c.advance(db, sample(1000, 500), now);
check(c.status(db, now).today_used == 0, 'activation baseline');
c.advance(db, sample(1100, 550), now + 10);
c.advance(db, sample(1100, 550), now + 20);
check(c.status(db, now + 20).today_used == 150, 'delta and duplicate sample');
c.advance(db, sample(5, 2), now + 30);
check(c.status(db, now + 30).today_used == 157, 'counter reset');
c.advance(db, null, now + 40);
c.advance(db, sample(10, 4), now + 50);
check(c.status(db, now + 50).today_used == 164, 'temporary missing device');
c.advance(db, sample(20, 10, 'B'), now + 60);
check(c.status(db, now + 60).today_used == 194, 'reboot current counters');
c.advance(db, sample(8, 3, 'B', 4), now + 70);
check(c.status(db, now + 70).today_used == 205, 'recreated device');
let cloned = json(sprintf('%J', db));
c.advance(cloned, sample(10, 4, 'B', 4), now + 80);
check(c.status(cloned, now + 80).today_used == 208, 'persistent round trip');

now = stamp(2026, 1, 31, 23, 59, 55); db = c.fresh(now);
c.advance(db, sample(0, 0), now);
c.advance(db, sample(1000, 200), now + 10);
check(db.days['2026-01-31'].rx == 500 && db.days['2026-02-01'].rx == 500, 'midnight split');
check(c.status(db, now + 10).month_used == 600, 'natural month rollover');
check(c.status(db, now + 10).cycle_used == 600, 'default cycle rollover');
let range = c.cycle(stamp(2026, 2, 28), 31);
check(range.start == '2026-02-28' && range.end == '2026-03-31', 'short month clamp');
range = c.cycle(stamp(2024, 2, 29), 31);
check(range.start == '2024-02-29' && range.end == '2024-03-31', 'leap year clamp');
range = c.cycle(stamp(2027, 1, 2), 15);
check(range.start == '2026-12-15' && range.end == '2027-01-15', 'cross-year cycle');

c.update_config(db, { monthly_gb:2, daily_gb:1, used_gb:1.5 }, now + 10);
check(c.status(db, now + 10).cycle_used == 1500000000, 'cycle usage calibration');
check(c.status(db, now + 10).today_used == 600, 'calibration does not corrupt day history');
check(c.status(db, now + 10).remaining == 500000000, 'decimal GB quota');
check(c.status(db, stamp(2026, 3, 1)).cycle_used == 0, 'calibration expires next cycle');
c.update_config(db, { count_mode:'rx', monthly_gb:0 }, now + 10);
check(c.status(db, now + 10).today_used == 500 && c.status(db, now + 10).remaining == null, 'direction and unlimited plan');
let rejected = false;
try { c.update_config(db, { reset_day:0 }, now); } catch (e) { rejected = true; }
check(rejected, 'invalid reset day rejected');
rejected = false;
try { c.update_config(db, { count_mode:'invalid' }, now); } catch (e) { rejected = true; }
check(rejected, 'invalid mode rejected');

db = c.fresh(0); c.advance(db, sample(0, 0), 0); c.advance(db, sample(300, 20), 10);
check(length(keys(db.days)) == 0 && db.pending_rx == 300, 'unsynced clock defers allocation');
c.advance(db, sample(400, 40), stamp(2026, 10, 7));
check(c.status(db, stamp(2026, 10, 7)).today_used == 440, 'NTP sync keeps pending bytes');
// Destructive reset is a new ledger with the old configuration and a fresh
// baseline; an uncommitted candidate must never mutate the caller's records.
now = stamp(2026, 10, 10);
db = c.fresh(now);
c.update_config(db, {plan_name:'custom', monthly_gb:120, daily_gb:5, reset_day:15,
    count_mode:'rx', device:'custom0', used_gb:12}, now);
c.advance(db, sample(1000,500), now);
c.advance(db, sample(1100,600), now+10);
db.pending_rx=20; db.pending_tx=30;
let before = sprintf('%J', db);
let cleared = c.clear_records(db, sample(1200,700), now+20);
check(sprintf('%J', db)==before, 'clear candidate does not mutate original');
check(sprintf('%J', cleared.config)==sprintf('%J', db.config), 'all configuration retained');
check(cleared.adjustment==null && cleared.pending_rx==0 && cleared.pending_tx==0, 'calibration and pending bytes cleared');
check(c.status(cleared,now+20).today_used==0 && c.status(cleared,now+20).month_used==0 &&
    c.status(cleared,now+20).cycle_used==0, 'all totals cleared');
check(cleared.last.rx==1200 && cleared.last.tx==700, 'current live baseline');
check(cleared.revision==1 && cleared.started_at==now+20, 'clear revision and start');
c.advance(cleared,sample(1230,710),now+30);
check(c.status(cleared,now+30).today_used==30, 'only post-clear delta');
let disk=json(sprintf('%J',cleared));
c.advance(disk,sample(1235,713),now+40);
check(c.status(disk,now+40).today_used==35, 'daemon restart keeps new baseline');
c.advance(disk,sample(4,2,'NEWBOOT'),now+50);
check(c.status(disk,now+50).today_used==39, 'reboot counts only new boot counters');
let no_interface=c.clear_records(db,null,now);
c.advance(no_interface,sample(999999,888888),now+10);
check(c.status(no_interface,now+10).today_used==0, 'unavailable interface never resurrects old counters');
c.advance(no_interface,sample(1000009,888899),now+20);
check(c.status(no_interface,now+20).today_used==10, 'sampling resumes after unavailable interface');
let unsynced=c.clear_records(db,sample(1200,700),0);
c.advance(unsynced,sample(1205,704),now);
check(c.status(unsynced,now).today_used==5, 'unsynced clear drops old pending bytes');
check(c.restore(db,cleared,now).revision==1, 'durable clear beats stale RAM');
check(c.restore(cleared,db,now).revision==1, 'new RAM beats old disk');
check(c.restore(db,null,now)==db && c.restore(null,db,now)==db, 'legacy and missing snapshot compatibility');
let latest=json(sprintf('%J',cleared)); latest.updated_at=now+100;
check(c.restore(latest,cleared,now).updated_at==now+100, 'equal revisions prefer newer RAM sample');
let again=c.clear_records(cleared,sample(1240,720),now+100);
check(again.revision==2 && c.status(again,now+100).cycle_used==0, 'repeated clear');
c.update_config(again,{device:'other0'},now+110);
check(again.last==null,'MU300 configurable interface resets baseline');
c.advance(again,{device:'other0',rx:99999,tx:99999,boot:'A',ifindex:42},now+120);
check(c.status(again,now+120).today_used==0,'changed interface does not import preexisting counters');
printf('traffic accounting: %d checks passed\n', checks);
