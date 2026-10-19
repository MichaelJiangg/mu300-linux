"""Selected U30 RAT, optional CEREG fields and failed reads do not fake LTE."""
from helpers import BIN, TOP, ShellTest

LIB = TOP / 'rootfs/overlay/opt/mu300/lib/network-led.sh'


class NetworkLamp(ShellTest):
    def test_registration_domains_and_optional_fields(self):
        cases = [
            ('+CEREG: 2,1,"10","20",7', 'online-4g'),
            ('+CEREG: 5,5,"10","20",11,0,0,"00100001","00000101"', 'online-5g'),
            ('+CEREG: 2,1,"10","20",7,0,13', 'online-4g'),
            ('+CEREG: 2,1,"10","20",7\n+C5GREG: 2,1,"10","20",11', 'online-5g'),
            ('+CEREG: 2,1,"10","20",7\n+C5GREG: 2,2', 'online-4g'),
            ('+CEREG: 0,1\n+C5GREG: 0,0', 'online-4g'),
            ('+CEREG: 2,1,"10","20",7\nERROR', 'online-4g'),
            ('+C5GREG: 2,5,"10","20",11', 'online-5g'),
            ('+CEREG: 2,1', ''),
            ('+CEREG: 2,2', ''),
            ('+CEREG: 1,"10","20",7', ''),
            ('+C5GREG: 2,0', ''),
            ('ERROR', ''),
            ('', ''),
        ]
        for shell in self.each_shell():
            for reply, expected in cases:
                r = self.sh(shell, f'. "{LIB}"; mu300_network_led_state', stdin=reply+'\n')
                self.assertEqual(r.stdout.strip(), expected, (reply, r.stderr))
                self.assertEqual(r.returncode == 0, bool(expected), reply)

    def test_u30_dialer_query_keeps_scope_and_failed_read_keeps_lamp(self):
        source = (BIN/'mobile-data').read_text()
        function = source[source.index('led_up() {'):source.index('\n# radio.log')]
        for shell in self.each_shell():
            for slot in (0, 1):
                self.stub('led-status', 'printf "%s\\n" "$*"')
                code = function + '''
DEVICE=u30air
at() { printf '%s\\n' "$*" >> "$STUBLOG/queries"; printf '%s\\n' "$TEST_REPLY"; }
led_up
'''
                r = self.sh(shell, code, MU300_NETWORK_LED_LIB=LIB, MU300_SIM_SLOT=slot,
                            TEST_REPLY='+CEREG: 2,1,"a","b",7\n+C5GREG: 2,1,"a","b",11')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout.strip(), 'online-5g')
                self.assertIn('AT+CEREG?;+C5GREG?', (self.tmp/'queries').read_text())
                r = self.sh(shell, code, MU300_NETWORK_LED_LIB=LIB, TEST_REPLY='ERROR')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout, '')

    def test_event_reconcile_uses_native_runtime_slot_instead_of_saved_default(self):
        source = (TOP/'openwrt/overlay/opt/mu300/bin/mu300-led-events').read_text()
        function = source[source.index('network_state() {'):source.index('\nnetwork_state\nwifi_state')]
        envlib = self.tmp/'sim-env'
        envlib.write_text('mu300_sim_env() { MU300_SIM_SLOT=1; MU300_SIM_SHARED=/run/mu300-at4; }\n')
        self.stub('mu300-device', 'echo u30air')
        self.stub('ubus', 'echo \'{"up": true}\'')
        self.stub('mu300-at', '''echo "$MU300_AT_DIR $*" > "$STUBLOG/commands"
printf '%s\n' '+CEREG: 2,1,"a","b",7' '+C5GREG: 2,1,"a","b",11' OK''')
        self.stub('led-status', 'echo "$*"')
        for shell in self.each_shell():
            r = self.sh(shell, function+'\nnetwork_state\n', MU300_SIM_ENV_LIB=envlib,
                        MU300_NETWORK_LED_LIB=LIB)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), 'online-5g')
            self.assertIn('/run/mu300-at4 -t 3 AT+SPACTCARD=1;', (self.tmp/'commands').read_text())
