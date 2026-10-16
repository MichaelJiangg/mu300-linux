"""Isolated netifd/data-card transactions: no radio, network, or real UCI."""
import json
from helpers import ShellTest, TOP

SCRIPT=TOP/'rootfs/overlay/opt/mu300/bin/mu300-data-sim'

class DataSim(ShellTest):
    def setUp(self):
        super().setUp()
        self.db=self.tmp/'state.json'
        self.envlib=self.tmp/'sim-env'
        self.envlib.write_text('''mu300_sim_env() {
MU300_SIM_DEVICE=card$1
MU300_SIM_SHARED=$STUBLOG/at
}
''')
        (self.tmp/'at').mkdir()
        import os
        os.mkfifo(self.tmp/'at/cmd')
        driver=self.tmp/'driver'
        driver.write_text('''#!/usr/bin/env python3
import json,sys,os
from pathlib import Path
p=Path(os.environ['STUBLOG']); f=p/'state.json'; s=json.loads(f.read_text())
name=sys.argv[1]; a=sys.argv[2:]
with (p/'commands').open('a') as log: log.write(name+' '+repr(a)+'\\n')
def save(): f.write_text(json.dumps(s))
if name=='uci':
 if a[:2]==['-q','get']:
  k=a[2].split('.')[-1]
  print({'data_sim':s['saved'],'sim_slots':s.get('slots',2),'data_interface':'wan'}.get(k,''))
 elif a[:2]==['-q','set']:
  s['saved']=int(a[2].split('=')[1]); save()
 elif a[:2]==['-q','commit'] and s.get('fail_commit'):
  s['fail_commit']=False; save(); sys.exit(1)
elif name=='ubus':
 print(json.dumps({'up':s['up'],'pending':False,'autostart':s.get('autostart',True),'l3_device':'card'+str(s['actual'])}))
elif name=='ifdown':
 if not s.get('stuck'): s['up']=False; save()
elif name=='ifup':
 if s['saved']!=1 or not s.get('fail_target'):
  s['actual']=s['saved']; s['up']=True; save()
elif name=='mu300-at':
 cmd=a[-1]
 if cmd.endswith('+SPSWDATA?'): print('+SPSWDATA: '+str(s['actual'])+'\\nOK')
 elif cmd.endswith('+CPIN?'):
  if s.get('absent_target') and 'SPACTCARD=1;' in cmd: print('+CME ERROR: 10')
  else: print('+CPIN: '+('SIM PIN' if s.get('pin') else 'READY')+'\\nOK')
 elif cmd.endswith('+SPSWDATA'):
  target=int(cmd.split('SPACTCARD=')[1][0])
  if not (target==1 and s.get('fail_switch')): s['actual']=target; save()
  print('OK')
elif name=='jsonfilter':
 try: print(str(json.load(sys.stdin)[a[-1][2:]]).lower())
 except: sys.exit(1)
''')
        driver.chmod(0o755)
        for name in ('uci','ubus','ifdown','ifup','mu300-at','jsonfilter'):
            self.stub(name,f'exec "{driver}" {name} "$@"')
        self.stub('sleep', ':')
        (self.tmp/'ready').touch()
        # BusyBox ash can run ifdown/ifup as applets before consulting PATH.
        # Keep all test network operations inside these explicit fixtures.
        self.controller=self.tmp/'data-sim'
        source=SCRIPT.read_text()
        shims='\n'.join(name+'() { "$STUBLOG/stubs/'+name+'" "$@"; }' for name in ('ifdown','ifup','sleep'))
        self.controller.write_text(source.replace('#!/bin/sh\n','#!/bin/sh\n'+shims+'\n',1))
        self.extra=dict(MU300_SIM_ENV_LIB=self.envlib,MU300_SIM_MUTEX=self.tmp/'mutex',MU300_DUAL_READY=self.tmp/'ready',MU300_DATA_SIM_ACTUAL=self.tmp/'actual')

    def reset(self, **values):
        self.db.write_text(json.dumps(dict(saved=0,actual=0,up=True,**values)))
        (self.tmp/'commands').write_text('')

    def run_switch(self,shell,target):
        return self.script(shell,self.controller,'apply',target,**self.extra)

    def test_same_card_never_disconnects(self):
        for shell in self.each_shell():
            self.reset()
            r=self.run_switch(shell,'0')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertNotIn('ifdown',(self.tmp/'commands').read_text())
            self.assertNotIn('ifup',(self.tmp/'commands').read_text())

    def test_validated_switch_and_reverse(self):
        for shell in self.each_shell():
            self.reset()
            for target in ('1','0'):
                r=self.run_switch(shell,target)
                self.assertEqual(r.returncode,0,r.stderr)
                s=json.loads(self.db.read_text())
                self.assertEqual((s['saved'],s['actual'],s['up']),(int(target),int(target),True))
            self.assertFalse((self.tmp/'mutex').exists())

    def test_manually_disabled_data_stays_off_on_other_card(self):
        for shell in self.each_shell():
            self.reset(autostart=False)
            state=json.loads(self.db.read_text());state['up']=False
            self.db.write_text(json.dumps(state))
            r=self.run_switch(shell,'1')
            self.assertEqual(r.returncode,0,r.stderr)
            state=json.loads(self.db.read_text())
            self.assertEqual((state['saved'],state['actual'],state['up']),(1,1,False))
            self.assertNotIn('ifup',(self.tmp/'commands').read_text())

    def test_failed_selection_restores_original(self):
        for shell in self.each_shell():
            self.reset(fail_switch=True)
            r=self.run_switch(shell,'1')
            self.assertNotEqual(r.returncode,0)
            self.assertIn('sim_switch_failed_restored',r.stderr)
            s=json.loads(self.db.read_text())
            self.assertEqual((s['saved'],s['actual'],s['up']),(0,0,True))

    def test_offline_card_can_be_selected_and_stays_selected(self):
        for shell in self.each_shell():
            self.reset(fail_target=True)
            r=self.run_switch(shell,'1')
            self.assertEqual(r.returncode,0,r.stderr)
            s=json.loads(self.db.read_text())
            self.assertEqual((s['saved'],s['actual'],s['up']),(1,1,False))
            r=self.script(shell,SCRIPT,'get',**self.extra)
            view=json.loads(r.stdout)
            self.assertEqual((view['saved_sim'],view['actual_sim'],view['data_connected']),(1,1,False))
            self.assertNotIn("mu300-at ['-t', '3', 'AT+SPACTCARD=0;+SPSWDATA?']",(self.tmp/'commands').read_text().split('ifup')[-1])

    def test_unready_and_invalid_inputs_do_not_disconnect(self):
        for shell in self.each_shell():
            for target in ('2','../1','1'):
                self.reset(pin=True)
                r=self.run_switch(shell,target)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('ifdown',(self.tmp/'commands').read_text())

    def test_mutex_refuses_concurrent_modem_changes(self):
        for shell in self.each_shell():
            self.reset()
            (self.tmp/'mutex').mkdir()
            r=self.run_switch(shell,'1')
            self.assertIn('modem_busy',r.stderr)
            self.assertNotIn('mu300-at',(self.tmp/'commands').read_text())
            (self.tmp/'mutex').rmdir()

    def test_missing_internal_card_is_reported_without_disconnecting_the_external_card(self):
        for shell in self.each_shell():
            self.reset(absent_target=True)
            r=self.run_switch(shell,'1')
            self.assertNotEqual(r.returncode,0)
            self.assertIn('sim_not_ready',r.stderr)
            self.assertNotIn('ifdown',(self.tmp/'commands').read_text())
            self.assertEqual(json.loads(self.db.read_text()),
                             dict(saved=0,actual=0,up=True,absent_target=True))
