"""U30 status events own three independent physical lamp groups."""
import os
import subprocess
from pathlib import Path
from helpers import BIN,ShellTest

class U30Leds(ShellTest):
    def setUp(self):
        super().setUp()
        self.root=self.tmp/'root';self.lamps=self.root/'sys/class/leds'
        for name in ['net_blue','zte-ldo0','zte-ldo1','zte-ldo2','keyboard-backlight','sc27xx:red','sc27xx:green','sc27xx:blue']:
            p=self.lamps/name;p.mkdir(parents=True)
            (p/'brightness').write_text('0\n');(p/'max_brightness').write_text('255\n' if name.startswith('sc27xx:') else '1\n');(p/'trigger').write_text('[none] timer\n')
        (self.root/'run/mu300').mkdir(parents=True);(self.root/'run/mu300/device').write_text('u30air\n')
        (self.root/'proc').mkdir();(self.root/'proc/uptime').write_text('100.00 999.00\n')
        self.battery=self.root/'sys/class/power_supply/sc27xx-fgu';self.battery.mkdir(parents=True)
        (self.battery/'capacity').write_text('65\n');(self.battery/'status').write_text('Charging\n')
        self.stub('uci',"""case "$3" in
 system.mu300_leds.timeout) echo "${TEST_TIMEOUT:-0}" ;;
 system.mu300_leds.signal) echo "${TEST_SIGNAL:-1}" ;;
 system.mu300_leds.wifi) echo "${TEST_WIFI:-1}" ;;
 system.mu300_leds.battery) echo "${TEST_BATTERY:-1}" ;;
 system.mu300_leds.battery_brightness) echo "${TEST_BRIGHTNESS:-255}" ;;
esac""")
        self.stub('iw','echo "channel 36 (5180 MHz)"')
        self.extra=dict(MU300_SYSROOT=self.root,MU300_BIN=BIN)

    def apply(self,shell,*args,**extra):
        r=self.script(shell,BIN/'u30air-led-status',*args,**dict(self.extra,**extra))
        self.assertEqual(r.returncode,0,r.stderr)
        return r.stdout.strip()

    def value(self,name):return (self.lamps/name/'brightness').read_text().strip()

    def test_events_do_not_confuse_network_with_battery_and_wifi(self):
        for shell in self.each_shell():
            self.apply(shell,'online-5g');self.apply(shell,'wifi-on')
            self.assertEqual([self.value(n) for n in ['net_blue','zte-ldo0','zte-ldo1','zte-ldo2']],['0','1','1','0'])
            self.assertEqual(self.value('sc27xx:blue'),'255');self.assertEqual(self.value('sc27xx:green'),'0')
            self.apply(shell,'online-4g')
            self.assertEqual(self.value('net_blue'),'1');self.assertEqual(self.value('zte-ldo0'),'0')
            self.assertEqual(self.value('zte-ldo1'),'1');self.assertEqual(self.value('sc27xx:blue'),'255')
            self.apply(shell,'offline');self.assertEqual(self.value('keyboard-backlight'),'1')
            self.apply(shell,'wifi-off');self.assertEqual(self.value('zte-ldo1'),'0')

    def test_controls_do_not_erase_desired_state(self):
        for shell in self.each_shell():
            self.apply(shell,'online-5g');self.apply(shell,'wifi-on')
            self.apply(shell,'refresh',TEST_SIGNAL='0',TEST_WIFI='0',TEST_BATTERY='0')
            self.assertTrue(all(self.value(n)=='0' for n in ['zte-ldo0','zte-ldo1','sc27xx:blue']))
            self.apply(shell,'refresh',TEST_BRIGHTNESS='40')
            self.assertEqual(self.value('zte-ldo0'),'1');self.assertEqual(self.value('zte-ldo1'),'1');self.assertEqual(self.value('sc27xx:blue'),'40')

    def test_battery_states_and_timeout(self):
        for shell in self.each_shell():
            (self.battery/'status').write_text('Discharging\n');(self.battery/'capacity').write_text('10\n')
            self.apply(shell,'battery');self.assertEqual(self.value('sc27xx:red'),'255')
            (self.battery/'status').write_text('Full\n');self.apply(shell,'battery')
            self.assertEqual(self.value('sc27xx:green'),'255');self.assertEqual(self.value('sc27xx:red'),'0')
            (self.battery/'status').write_text('Discharging\n')
            self.apply(shell,'online-5g',TEST_TIMEOUT='60')
            self.assertEqual(self.value('zte-ldo0'),'0')
            r=self.script(shell,BIN/'mu300-led','wake',**dict(self.extra,TEST_TIMEOUT='60'));self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(self.value('zte-ldo0'),'1')
            self.apply(shell,'current',TEST_TIMEOUT='60');self.assertEqual(self.value('zte-ldo0'),'1')
            self.script(shell,BIN/'mu300-led','sleep',**dict(self.extra,TEST_TIMEOUT='60'));self.assertEqual(self.value('zte-ldo0'),'0')

    def test_power_holds_lamps_and_unplug_restarts_timeout(self):
        for shell in self.each_shell():
            online=self.root/'sys/class/power_supply/bq256xx-charger/online';online.parent.mkdir(exist_ok=True);online.write_text('1\n')
            (self.battery/'status').write_text('Charging\n')
            self.apply(shell,'online-5g',TEST_TIMEOUT='60');self.apply(shell,'wifi-on',TEST_TIMEOUT='60')
            (self.root/'proc/uptime').write_text('10000.00 0.00\n')
            self.script(shell,BIN/'mu300-led','sleep','--if-due',**dict(self.extra,TEST_TIMEOUT='60'))
            self.assertEqual(self.value('zte-ldo0'),'1');self.assertEqual(self.value('zte-ldo1'),'1')
            online.write_text('0\n');(self.battery/'status').write_text('Discharging\n')
            self.apply(shell,'battery',TEST_TIMEOUT='60')
            self.assertEqual((self.root/'run/mu300/led/.awake-until').read_text().strip(),'10060')
            (self.root/'proc/uptime').write_text('10061.00 0.00\n')
            self.script(shell,BIN/'mu300-led','sleep','--if-due',**dict(self.extra,TEST_TIMEOUT='60'))
            self.assertEqual(self.value('zte-ldo0'),'0');self.assertEqual(self.value('zte-ldo1'),'0')
            self.assertTrue(all(self.value(n)=='0' for n in ['sc27xx:red','sc27xx:green','sc27xx:blue']))
            online.write_text('1\n');(self.battery/'status').write_text('Charging\n')
            self.apply(shell,'battery',TEST_TIMEOUT='60')
            self.assertEqual(self.value('zte-ldo0'),'1');self.assertEqual(self.value('zte-ldo1'),'1')

    def test_charging_uses_hardware_rise_hold_fall_rest(self):
        for shell in self.each_shell():
            blue=self.lamps/'sc27xx:blue'
            (blue/'trigger').write_text('[none] timer pattern\n');(blue/'hw_pattern').write_text('');(blue/'repeat').write_text('0\n')
            self.apply(shell,'battery',TEST_BRIGHTNESS='40')
            self.assertEqual((blue/'trigger').read_text().strip(),'pattern')
            self.assertEqual((blue/'hw_pattern').read_text().strip(),'0 625 40 750 0 625 0 250')
            self.assertEqual((blue/'repeat').read_text().strip(),'-1')
            self.assertFalse((blue/'delay_on').exists())
            (self.battery/'status').write_text('Full\n');self.apply(shell,'battery')
            self.assertEqual((blue/'trigger').read_text().strip(),'none');self.assertEqual(self.value('sc27xx:green'),'255')
            (self.battery/'status').write_text('Charging\n')

    def test_unplug_ignores_stale_fgu_charging_and_stays_dark_after_events(self):
        for shell in self.each_shell():
            online=self.root/'sys/class/power_supply/bq256xx-charger/online'
            online.parent.mkdir(exist_ok=True);online.write_text('1\n')
            (self.root/'proc/uptime').write_text('100.00 0.00\n')
            self.apply(shell,'online-5g',TEST_TIMEOUT='60')
            self.apply(shell,'wifi-on',TEST_TIMEOUT='60')
            online.write_text('0\n') # FGU deliberately still reports Charging.
            self.apply(shell,'battery',TEST_TIMEOUT='60')
            self.assertEqual(self.value('sc27xx:blue'),'0')
            self.assertEqual(self.value('sc27xx:green'),'255')
            self.assertFalse((self.root/'run/mu300/led/.battery-breathe').exists())
            (self.root/'proc/uptime').write_text('161.00 0.00\n')
            self.script(shell,BIN/'mu300-led','sleep','--if-due',**dict(self.extra,TEST_TIMEOUT='60'))
            self.apply(shell,'refresh',TEST_TIMEOUT='60')
            self.assertTrue(all(self.value(n)=='0' for n in ['zte-ldo0','zte-ldo1','sc27xx:red','sc27xx:green','sc27xx:blue']))

    def test_queued_power_event_reads_online_after_timeout_lock(self):
        import fcntl,time
        for shell in self.each_shell():
            online=self.root/'sys/class/power_supply/bq256xx-charger/online'
            online.parent.mkdir(exist_ok=True);online.write_text('1\n')
            self.apply(shell,'online-5g',TEST_TIMEOUT='60')
            state=self.root/'run/mu300/led'
            with (state/'.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                proc=subprocess.Popen(shell+[str(BIN/'mu300-led'),'battery'],env=self.env(**dict(self.extra,TEST_TIMEOUT='60')),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    time.sleep(.1)
                    self.assertIsNone(proc.poll(),'battery event bypassed shared LED lock')
                    online.write_text('0\n')
                    (state/'.external-power').write_text('0\n')
                    (state/'.awake-until').unlink(missing_ok=True)
                    fcntl.flock(lock,fcntl.LOCK_UN)
                    out,err=proc.communicate(timeout=10)
                    self.assertEqual(proc.returncode,0,err)
                finally:
                    if proc.poll() is None:proc.kill();proc.communicate()
            self.assertTrue(all(self.value(n)=='0' for n in ['sc27xx:red','sc27xx:green','sc27xx:blue']))
