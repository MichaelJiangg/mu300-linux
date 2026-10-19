"""V50's two network banks and hotspot bank do not overwrite one another."""
import os
from helpers import ShellTest, TOP

SCRIPT=TOP/'rootfs/overlay/opt/mu300/bin/v50-led-status'

class V50Leds(ShellTest):
    def setUp(self):
        super().setUp()
        self.leds=self.tmp/'leds'; self.run=self.tmp/'run';self.run.mkdir()
        for bank in ('net1','net2','wifi'):
            for color,maximum in [('red',120),('white',80),('blue',120)]:
                p=self.leds/f'v50:{bank}:{color}';p.mkdir(parents=True)
                (p/'brightness').write_text('0\n');(p/'trigger').write_text('none timer\n')
                (p/'max_brightness').write_text(str(maximum))
        self.stub('uci','''case "$3" in
 *.signal) echo "${TEST_SIGNAL:-1}" ;;
 *.signal2) echo "${TEST_SIGNAL2:-1}" ;;
 *.signal_brightness) echo "${TEST_BRIGHTNESS:-255}" ;;
 *.signal2_brightness) echo 128 ;;
 *.wifi) echo 1 ;;
 *.wifi_brightness) echo 255 ;;
 *.data_sim) echo "${TEST_SIM:-0}" ;;
 esac''')
        self.stub('mu300-at','echo unexpected_at_query >> "$STUBLOG/commands"; exit 1')
        self.extra=dict(MU300_LED_SYSFS_ROOT=self.leds,MU300_LED_RUN_DIR=self.run,MU300_LED_WIFI_FREQ='5200')

    def values(self,bank):
        return tuple(int((self.leds/f'v50:{bank}:{c}'/'brightness').read_text()) for c in ('red','white','blue'))

    def call(self,shell,*args,**env):
        r=self.script(shell,SCRIPT,*args,**dict(self.extra,**env))
        self.assertEqual(r.returncode,0,r.stderr)

    def test_registration_and_wifi_are_independent_without_at_queries(self):
        for shell in self.each_shell():
            self.call(shell,'sim-status','0','+CEREG: 1,"0012","abcd",7')
            self.assertEqual(self.values('net2'),(0,0,60))
            self.call(shell,'sim-status','1','+CEREG: 2,1,"0012","abcd",11','1')
            self.assertEqual(self.values('net1'),(0,80,0))
            self.call(shell,'wifi-on')
            self.assertEqual(self.values('wifi'),(0,80,0))
            self.call(shell,'wifi-on',MU300_LED_WIFI_FREQ='2412')
            self.assertEqual(self.values('wifi'),(0,0,120))
            self.call(shell,'sim-status','0','+CEREG: 2')
            self.assertEqual(self.values('net2'),(60,0,0))
            self.assertEqual(self.values('net1'),(0,80,0))
            self.assertEqual(self.values('wifi'),(0,0,120))
            self.assertFalse((self.tmp/'commands').exists())

    def test_settings_refresh_and_data_sim_ownership(self):
        for shell in self.each_shell():
            self.call(shell,'online-4g',TEST_SIM='1')
            self.assertEqual(self.values('net1'),(0,0,120))
            self.call(shell,'online-5g',TEST_SIM='0')
            self.call(shell,'refresh',TEST_SIGNAL='0',TEST_SIGNAL2='0')
            self.assertEqual(self.values('net1'),(0,0,0))
            self.assertEqual(self.values('net2'),(0,0,0))
            self.call(shell,'refresh',TEST_BRIGHTNESS='64')
            self.assertEqual(self.values('net1'),(0,0,30))
            self.assertEqual(self.values('net2'),(0,40,0))
            alarm=self.run/'mu300/thermal-alarm';alarm.parent.mkdir(exist_ok=True);alarm.touch()
            self.call(shell,'refresh')
            self.assertEqual(self.values('net1'),(120,0,0))
            alarm.unlink();self.call(shell,'refresh')
            self.assertEqual(self.values('net1'),(0,0,120))

    def test_bad_and_short_responses_preserve_the_last_status(self):
        for shell in self.each_shell():
            self.call(shell,'sim-status','1','+CEREG: 5,"0012","abcd",11')
            self.call(shell,'sim-status','1','+CEREG: 5')
            self.assertEqual(self.values('net1'),(0,80,0))
            self.call(shell,'sim-status','1','+CME ERROR: 3')
            self.assertEqual(self.values('net1'),(0,80,0))

    def test_boot_presence_event_clears_empty_lamp_and_emergency_is_offline(self):
        for shell in self.each_shell():
            self.call(shell,'boot')
            self.call(shell,'sim-presence','0','absent')
            self.assertEqual(self.values('net2'),(0,0,0))
            self.call(shell,'sim-status','0','+CEREG: 0')
            self.assertEqual(self.values('net2'),(0,0,0))
            self.call(shell,'sim-presence','1','present')
            self.call(shell,'sim-status','1','+CEREG: 2,8,"0012","abcd",11','1')
            self.assertEqual(self.values('net1'),(120,0,0))
            self.call(shell,'sim-status','1','+CEREG: 1,"0012","abcd",11')
            self.call(shell,'sim-presence','1','present')
            self.assertEqual(self.values('net1'),(0,80,0))
            self.assertFalse((self.tmp/'commands').exists())
