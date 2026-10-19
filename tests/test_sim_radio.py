"""Persistent RF controls through fake existing owners; never access hardware."""
import json
import re
import fcntl
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
        self.stub('flock', '''exec python3 -c 'import fcntl,sys
try: fcntl.flock(int(sys.argv[-1]),fcntl.LOCK_EX|fcntl.LOCK_NB)
except OSError: sys.exit(1)' "$@"''')
        self.stub('ubus','printf "%s\\n" "$*" >> "$STUBLOG/ubus"; echo "{}"')
        self.stub('mu300-at', '''exec python3 -c '
import os,json,sys,re
from pathlib import Path
r=Path(os.environ["STUBLOG"]);p=r/"state";s=json.loads(p.read_text());cmd=sys.argv[-1]
with (r/"at").open("a") as f:f.write(cmd+"\\n")
n=int(re.search(r"SPACTCARD=(\\d)",cmd)[1])
if "SFUN=" in cmd:
 if os.getenv("FAIL_RF")=="1":print("ERROR");sys.exit(1)
 s[n]=1 if cmd.endswith("=4") else int(os.getenv("OFF_STATE","2"));p.write_text(json.dumps(s))
elif cmd.endswith("+CPIN?"): print("+CPIN: READY" if os.getenv("SIM_POWERED")=="1" else "+CME ERROR: 10")
else: print("+CFUN: "+str(s[n]))
print("OK")' "$@"''')
        self.stub('mobile-data', '''printf '%s\n' "$*" >> "$STUBLOG/mobile"
case $1 in
 radio-policy) exec sh "$CONTROLLER" --locked "$2" "$3";;
 radio-on) printf '[1,2]' > "$STUBLOG/state";;
 *) exit 2;;
esac''')
        self.controller=self.tmp/'controller'
        source=SCRIPT.read_text().replace('/opt/mu300/bin/mu300-sim-env',str(env))
        source=source.replace('/opt/mu300/bin/mobile-data','"$STUBLOG/stubs/mobile-data"')
        source=source.replace('sync -f "$policy"','"$STUBLOG/stubs/sync" -f "$policy"')
        self.controller.write_text(source)
        (self.tmp/'handshake').touch()
        self.env_extra=dict(CONTROLLER=self.controller,MU300_SIM_MUTEX=self.tmp/'gate',MU300_RIL_HANDSHAKE=self.tmp/'handshake',MU300_SIM_CONTROL_LOCK=self.tmp/'native-control.lock')
        (self.tmp/'state').write_text('[1,1]')

    def call(self,shell,*args,**extra):
        return self.script(shell,self.controller,*args,**dict(self.env_extra,**extra))

    def test_independent_radios_both_off_and_reenable_without_data_switch(self):
        for shell in self.each_shell():
            for slot,on,expected in [('1','0',[1,2]),('0','0',[2,2]),('1','1',[2,1]),('0','1',[1,1])]:
                result=self.call(shell,'apply',slot,on)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads((self.tmp/'state').read_text()),expected)
            self.assertEqual(json.loads(self.call(shell,'get').stdout)['enabled'],[1,1])
            self.assertNotIn('SPSWDATA',(self.tmp/'at').read_text())
            self.assertNotIn('CFUN=',(self.tmp/'at').read_text())
            notifications=(self.tmp/'ubus').read_text()
            self.assertIn('"available":false',notifications)
            self.assertIn('"available":true',notifications)

    def test_missing_policy_defaults_sim2_off_and_keeps_saved_sim2_selection(self):
        for shell in self.each_shell():
            (self.tmp/'sim-radio-policy').unlink(missing_ok=True)
            self.stub('uci','case "$3" in *.sim_slots) echo 2;; *.data_sim) echo "${SAVED_DATA_SIM:-0}";; *) echo wan;; esac')
            view=json.loads(self.call(shell,'get').stdout)
            self.assertEqual(view['enabled'],[1,0])
            view=json.loads(self.call(shell,'get',SAVED_DATA_SIM='1').stdout)
            self.assertEqual(view['enabled'],[1,1])
            self.assertFalse((self.tmp/'at').exists())
            (self.tmp/'sim-radio-policy').write_text('1 0\n')
            self.assertEqual(json.loads(self.call(shell,'get',SAVED_DATA_SIM='1').stdout)['enabled'],[1,0])

    def test_explicit_sim2_switch_enables_under_existing_switch_gate(self):
        for shell in self.each_shell():
            (self.tmp/'sim-radio-policy').write_text('1 0\n')
            (self.tmp/'state').write_text('[1,2]')
            gate=self.tmp/'gate';gate.mkdir(exist_ok=True)
            result=self.call(shell,'--switch-enable','1','1')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((self.tmp/'sim-radio-policy').read_text(),'1 1\n')
            self.assertEqual(json.loads((self.tmp/'state').read_text()),[1,1])
            self.assertTrue(gate.exists())
            gate.rmdir()
            self.assertNotIn('SPSWDATA',(self.tmp/'at').read_text())

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
            (self.tmp/'state').write_text('[0,2]')
            (self.tmp/'sim-radio-policy').write_text('0 0\n')
            result=self.call(shell,'apply','0','1')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('radio-on',(self.tmp/'mobile').read_text())
            self.assertEqual(json.loads((self.tmp/'state').read_text()),[1,2])

    def test_cold_disable_never_preempts_first_ril_handshake(self):
        for shell in self.each_shell():
            (self.tmp/'handshake').unlink(missing_ok=True)
            result=self.call(shell,'apply','0','0')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((self.tmp/'at').exists())

    def test_sfun_off_zero_and_two_reenable_without_resetting_powered_sim(self):
        for shell in self.each_shell():
            for off in ('0','2'):
                (self.tmp/'state').write_text('[1,1]')
                self.assertEqual(self.call(shell,'apply','0','0',OFF_STATE=off).returncode,0)
                self.assertEqual(json.loads((self.tmp/'state').read_text()),[int(off),1])
                result=self.call(shell,'apply','0','1',SIM_POWERED='1')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads((self.tmp/'state').read_text()),[1,1])
                self.assertNotIn('radio-on',(self.tmp/'mobile').read_text())
                commands=(self.tmp/'at').read_text()
                self.assertIn('AT+SPACTCARD=0;+SFUN=5',commands)
                self.assertIn('AT+SPACTCARD=0;+SFUN=4',commands)
                self.assertNotIn('CFUN=',commands)

    def test_old_flight_mode_is_not_accepted_as_sfun_off_confirmation(self):
        for shell in self.each_shell():
            result=self.call(shell,'apply','1','0',OFF_STATE='4')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('readback not confirmed',result.stderr)
            self.assertEqual((self.tmp/'sim-radio-policy').read_text(),'1 0\n')

    def test_enabling_already_on_sim_only_updates_permission(self):
        for shell in self.each_shell():
            (self.tmp/'state').write_text('[1,1]')
            (self.tmp/'sim-radio-policy').write_text('1 0\n')
            result=self.call(shell,'apply','1','1')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((self.tmp/'sim-radio-policy').read_text(),'1 1\n')
            self.assertNotIn('SFUN=',(self.tmp/'at').read_text())

    def test_u30_inactive_permission_changes_preserve_cold_stack_baseline(self):
        self.stub('mu300-device','echo u30air')
        for shell in self.each_shell():
            (self.tmp/'state').write_text('[1,0]')
            for enabled in ('0','1'):
                result=self.call(shell,'apply','1',enabled)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads((self.tmp/'state').read_text()),[1,0])
                self.assertEqual((self.tmp/'sim-radio-policy').read_text(),f'1 {enabled}\n')
                self.assertFalse((self.tmp/'at').exists())
                self.assertFalse((self.tmp/'ubus').exists())

    def test_single_sim_radio_jobs_do_not_require_dual_sim_switch_adapter(self):
        source=(TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/data-sim').read_text()
        function=re.search(r'validate_apply\(\) \{.*?^\}',source,re.M|re.S)[0]
        function=function.replace('/opt/mu300/bin/mu300-sim-radio',str(self.stubs/'mobile-data'))
        self.stub('uci','echo "${SIM_SLOTS:-1}"')
        for shell in self.each_shell():
            for slots in ('1','2'):
                for slot in ('0','1'):
                    code=function+'\nadapter=/missing/data-sim\nvalidate_apply data radio-'+slot+'-0\n'
                    result=self.sh(shell,code,SIM_SLOTS=slots)
                    self.assertEqual(result.returncode==0,slot=='0' or slots=='2')

    def test_native_switch_lock_blocks_rf_without_changing_intent(self):
        self.stub('mu300-device','echo u30air')
        with (self.tmp/'native-control.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            for shell in self.each_shell():
                result=self.call(shell,'apply','0','0')
                self.assertNotEqual(result.returncode,0)
                self.assertIn('modem_busy',result.stderr)
                self.assertFalse((self.tmp/'sim-radio-policy').exists())
                self.assertFalse((self.tmp/'at').exists())
