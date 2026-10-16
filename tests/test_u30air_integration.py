"""U30-specific boot routing and the existing zero-based dashboard contract."""
import json
from pathlib import Path
from helpers import BIN, TOP, ShellTest

class U30Adapter(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('mu300-device', 'echo "${TEST_DEVICE:-u30air}"')
        self.stub('native', """echo "$*" >> "$STUBLOG/native-calls"
case "$1" in
 status) echo '{"ok":1,"active":2,"default":1,"hot":1,"available":1,"wan_up":true}' ;;
 *) echo '{"ok":1}' ;;
esac""")
        self.stub('jsonfilter', r"""exec python3 -c 'import json,sys; v=json.load(sys.stdin).get(sys.argv[-1][2:]); print(str(v).lower() if v is not None else "")' "$@"
""")
        self.extra=dict(MU300_NATIVE_SIM_CMD=self.stubs/'native',MU300_SIM_MUTEX=self.tmp/'switch')

    def test_existing_dashboard_schema_uses_zero_based_slots(self):
        for shell in self.each_shell():
            r=self.script(shell,BIN/'mu300-data-sim-u30','get',**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            status=json.loads(r.stdout)
            self.assertEqual((status['actual_sim'],status['saved_sim']),(1,0))
            self.assertTrue(status['ready']);self.assertTrue(status['data_connected'])
            self.assertTrue(status['native'])

    def test_switch_and_boot_policy_have_distinct_operations(self):
        for shell in self.each_shell():
            for value,call in [('0','switch 1'),('1','switch 2'),('u30-hot-1','hot 1'),('u30-default-1','default 2')]:
                r=self.script(shell,BIN/'mu300-data-sim-u30','apply',value,**self.extra)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual((self.tmp/'native-calls').read_text().splitlines()[-1],call)
                self.assertFalse((self.tmp/'switch').exists())

    def test_other_boards_and_injection_never_call_native_controller(self):
        for shell in self.each_shell():
            for value in ('2','u30-hot-2','u30-default-1;reboot','../1'):
                r=self.script(shell,BIN/'mu300-data-sim-u30','apply',value,**self.extra)
                self.assertNotEqual(r.returncode,0)
            r=self.script(shell,BIN/'mu300-data-sim-u30','apply','1',TEST_DEVICE='v50',**self.extra)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse((self.tmp/'native-calls').exists())

class U30Init(ShellTest):
    def setUp(self):
        super().setUp()
        self.run=self.tmp/'run'; (self.run/'mu300').mkdir(parents=True)
        self.etc=self.tmp/'etc';self.etc.mkdir()
        self.stub('uci', """case "$*" in
 '-q get unisoc_modem.main.data_sim') echo "${TEST_SLOT:-1}" ;;
 '-q get unisoc_modem.main.u30_sim_hot') echo "${TEST_HOT:-0}" ;;
 '-q get unisoc_modem.main.sim_slots') echo 2 ;;
 *) exit 1 ;;
esac""")
        self.stub('mu300-device', 'echo "${TEST_DEVICE:-u30air}"')
        self.init=self.tmp/'init'
        source=(TOP/'openwrt/overlay/etc/init.d/mu300-atd').read_text()
        source=source.replace('/run/',str(self.run)+'/').replace('/etc/',str(self.etc)+'/')
        source=source.replace('/opt/mu300/bin/mu300-device','mu300-device')
        # Source is exercised with real policy, mocked procd and no real device files.
        harness="""
procd_open_instance() { echo "instance $*"; }
procd_set_param() { echo "param $*"; }
procd_close_instance() { :; }
"""
        self.init.write_text(harness+source+'\nstart_service\n')
        self.extra=dict(MU300_SIM_CONFIG_LIB=TOP/'rootfs/overlay/opt/mu300/lib/sim-config.sh',MU300_SIM_ROOT=self.tmp)

    def test_native_owners_are_unique_bounded_and_keep_sms_slot_mapping(self):
        for shell in self.each_shell():
            for f in ('sim-slot','sim-boot-policy'):(self.run/'mu300'/f).unlink(missing_ok=True)
            (self.etc/'mu300-sim-pending').unlink(missing_ok=True)
            r=self.script(shell,self.init,**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            instances=[l for l in r.stdout.splitlines() if l.startswith('instance ')]
            self.assertEqual(instances,['instance atd','instance atd2','instance atd4','instance atd5','instance sim2-cold-start'])
            self.assertNotIn('param respawn',r.stdout)
            self.assertEqual(r.stdout.count('MU300_AT_DISABLE_REOPEN=1'),4)
            for line in r.stdout.splitlines():
                if line.startswith('param command /bin/sh'):
                    self.assertIn('sbuf_5_006, state: 1,',line)
                    self.assertIn('-gt 240',line)
                if line.startswith('param env'):
                    self.assertNotIn('sms/sim0',line)
                    self.assertIn('MU300_SMS_POOL=',line)
            self.assertTrue((self.etc/'mu300-sim-pending').exists())

    def test_f50_and_v50_keep_legacy_path(self):
        for shell in self.each_shell():
            for board in ('f50','v50'):
                r=self.script(shell,self.init,TEST_DEVICE=board,**self.extra)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertNotIn('instance sim2-cold-start',r.stdout)
                self.assertIn('param respawn',r.stdout)
                self.assertFalse((self.etc/'mu300-sim-pending').exists())

    def test_generated_sbuf_waits_reach_exec(self):
        r=self.script(['bash'],self.init,**self.extra)
        import re
        for line in r.stdout.splitlines():
            if not line.startswith('param command /bin/sh -c '):continue
            code=line.removeprefix('param command /bin/sh -c ')
            code=re.sub(r'\[ -c /dev/stty_nr[1245] \]','true',code)
            code=code.replace("[ -c /dev/sipc_sbuf ] && grep -q '^sbuf_5_006, state: 1,' /dev/sipc_sbuf",'true')
            code=code.replace('exec /opt/mu300/bin/mu300-atd','echo ready')
            for shell in self.each_shell():
                result=self.sh(shell,'sleep() { exit 97; }; '+code)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),'ready')

class U30RuntimePin(ShellTest):
    def test_runtime_pin_wins_over_next_boot_choice_only_on_u30(self):
        self.stub('mu300-device','echo "${TEST_DEVICE:-u30air}"')
        self.stub('uci','case "$3" in *.data_sim) echo 1;; *.sim_slots) echo 2;; esac')
        pin=self.tmp/'sim-slot';pin.write_text('0\n')
        envlib=self.tmp/'sim-env'
        envlib.write_text((BIN/'mu300-sim-env').read_text().replace('/run/mu300/sim-slot',str(pin)))
        for shell in self.each_shell():
            for board,expected in [('u30air','0'),('v50','1')]:
                r=self.sh(shell,f'. "{envlib}"; mu300_sim_env; echo "$MU300_SIM_SLOT"',MU300_DEVICE_CMD=self.stubs/'mu300-device',TEST_DEVICE=board)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual(r.stdout.strip(),expected)

class U30ATGate(ShellTest):
    def test_native_sequence_and_unknown_radio_block_foreign_commands(self):
        run=self.tmp/'run'; (run/'mu300').mkdir(parents=True)
        client=self.tmp/'mu300-at'
        client.write_text((BIN/'mu300-at').read_text().replace('/run/',str(run)+'/'))
        for marker in ('sim-sequence','sim-active-unknown'):
            p=run/'mu300'/marker;p.touch()
            r=self.script(['bash'],client,'AT+CFUN?',MU300_AT_DIR=self.tmp/'no-broker')
            self.assertNotEqual(r.returncode,0);self.assertIn('busy',r.stderr)
            p.unlink()
        (run/'mu300/u30-native').touch()
        r=self.script(['bash'],client,'AT+CFUN?',MU300_AT_DIR=self.tmp/'no-broker')
        self.assertNotEqual(r.returncode,0);self.assertIn('direct tty fallback disabled',r.stderr)
