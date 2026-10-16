"""Persistent RF controls through fake existing owners; never access hardware."""
import json
from helpers import ShellTest, TOP

SCRIPT=TOP/'rootfs/overlay/opt/mu300/bin/mu300-sim-radio'


class SimRadio(ShellTest):
    def setUp(self):
        super().setUp()
        env=self.tmp/'sim-env'
        env.write_text('mu300_sim_env() { MU300_SIM_SLOT=${1:-0}; MU300_SIM_SHARED=slot$MU300_SIM_SLOT; export MU300_SIM_SLOT MU300_SIM_SHARED; }\n')
        self.stub('uci','echo wan')
        self.stub('mu300-device','echo f50')
        self.stub('sync',':')
        self.stub('ubus','printf "%s\\n" "$*" >> "$STUBLOG/ubus"; echo "{}"')
        self.stub('mu300-at', '''exec python3 -c '
import os,json,sys,re
from pathlib import Path
r=Path(os.environ["STUBLOG"]);p=r/"state";s=json.loads(p.read_text());cmd=sys.argv[-1]
with (r/"at").open("a") as f:f.write(cmd+"\\n")
n=int(re.search(r"SPACTCARD=(\\d)",cmd)[1])
if "CFUN=" in cmd:
 if os.getenv("FAIL_RF")=="1":print("ERROR");sys.exit(1)
 s[n]=int(cmd[-1]);p.write_text(json.dumps(s))
else: print("+CFUN: "+str(s[n]))
print("OK")' "$@"''')
        self.stub('mobile-data', '''printf '%s\n' "$*" >> "$STUBLOG/mobile"
case $1 in
 radio-policy) exec sh "$CONTROLLER" --locked "$2" "$3";;
 radio-on) printf '[1,4]' > "$STUBLOG/state";;
 *) exit 2;;
esac''')
        self.controller=self.tmp/'controller'
        source=SCRIPT.read_text().replace('/opt/mu300/bin/mu300-sim-env',str(env))
        source=source.replace('/opt/mu300/bin/mobile-data','"$STUBLOG/stubs/mobile-data"')
        source=source.replace('sync -f "$policy"','"$STUBLOG/stubs/sync" -f "$policy"')
        self.controller.write_text(source)
        (self.tmp/'handshake').touch()
        self.env_extra=dict(CONTROLLER=self.controller,MU300_SIM_MUTEX=self.tmp/'gate',MU300_RIL_HANDSHAKE=self.tmp/'handshake')
        (self.tmp/'state').write_text('[1,1]')

    def call(self,shell,*args,**extra):
        return self.script(shell,self.controller,*args,**dict(self.env_extra,**extra))

    def test_independent_radios_both_off_and_reenable_without_data_switch(self):
        for shell in self.each_shell():
            for slot,on,expected in [('1','0',[1,4]),('0','0',[4,4]),('1','1',[4,1]),('0','1',[1,1])]:
                result=self.call(shell,'apply',slot,on)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads((self.tmp/'state').read_text()),expected)
            self.assertEqual(json.loads(self.call(shell,'get').stdout)['enabled'],[1,1])
            self.assertNotIn('SPSWDATA',(self.tmp/'at').read_text())
            self.assertNotIn('SFUN',(self.tmp/'at').read_text())
            notifications=(self.tmp/'ubus').read_text()
            self.assertIn('"available":false',notifications)
            self.assertIn('"available":true',notifications)

    def test_standby_toggle_never_changes_wan_intent(self):
        for shell in self.each_shell():
            for state in ('0','1'):
                result=self.call(shell,'apply','1',state)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((self.tmp/'ubus').exists())

    def test_failure_keeps_saved_off_and_cleans_switch_gate(self):
        for shell in self.each_shell():
            result=self.call(shell,'apply','1','0',FAIL_RF='1')
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((self.tmp/'sim-radio-policy').read_text(),'1 0\n')
            self.assertFalse((self.tmp/'gate').exists())

    def test_corrupt_policy_and_invalid_arguments_send_no_at(self):
        for shell in self.each_shell():
            (self.tmp/'sim-radio-policy').write_text('broken')
            self.assertNotEqual(self.call(shell,'apply','0','1').returncode,0)
            self.assertNotEqual(self.call(shell,'apply','2','1').returncode,0)
            self.assertFalse((self.tmp/'at').exists())

    def test_cold_reenable_uses_existing_initializer_and_not_new_sfun_sequence(self):
        for shell in self.each_shell():
            (self.tmp/'state').write_text('[0,4]')
            (self.tmp/'sim-radio-policy').write_text('0 0\n')
            result=self.call(shell,'apply','0','1')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('radio-on',(self.tmp/'mobile').read_text())
            self.assertEqual(json.loads((self.tmp/'state').read_text()),[1,4])

    def test_cold_disable_never_preempts_first_ril_handshake(self):
        for shell in self.each_shell():
            (self.tmp/'handshake').unlink(missing_ok=True)
            result=self.call(shell,'apply','0','0')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((self.tmp/'at').exists())
