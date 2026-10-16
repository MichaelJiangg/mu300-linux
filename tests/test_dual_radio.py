import json
import os
from helpers import ShellTest, TOP

SCRIPT=TOP/'rootfs/overlay/opt/mu300/bin/mu300-dual-radio'

class DualRadio(ShellTest):
    def setUp(self):
        super().setUp()
        self.run=self.tmp/'run'
        for directory,n in [('mu300-at',0),('mu300-at4',3)]:
            p=self.run/directory/'urc';p.mkdir(parents=True)
            (p/f'stty_nr{n}.ready').write_text(str(os.getpid()))
        client=self.tmp/'client'
        client.write_text('''#!/usr/bin/env python3
import json,os,sys,re
from pathlib import Path
p=Path(os.environ['STUBLOG']);f=p/'radio.json';s=json.loads(f.read_text());cmd=sys.argv[-1]
with (p/'commands').open('a') as log:log.write(cmd+'\\n')
slot=int(re.search(r'SPACTCARD=(\\d)',cmd)[1])
if cmd.endswith('+CFUN?'):print('+CFUN: '+str(s['cfun'][slot]))
elif cmd.endswith('+CPIN?'):print('+CPIN: READY' if slot in s.get('present',[0,1]) else '+CME ERROR: 10')
elif cmd.endswith('+SPTESTMODE?'):print('+SPTESTMODE: 134,128,1,20,3,1')
elif cmd.endswith('+SPSWDATA?'):print('+SPSWDATA: '+str(s['data']))
elif cmd.endswith('+SPSWDATA'):s['data']=slot
elif cmd.endswith('+SFUN=4'):s['cfun'][slot]=1
elif cmd.endswith('+SFUN=2'):s['cfun'][slot]=0
elif cmd.endswith('+CFUN=4'):s['cfun'][slot]=4
f.write_text(json.dumps(s));print('OK')
''')
        client.chmod(0o755)
        self.extra=dict(MU300_DUAL_AT_CLIENT=client,MU300_DUAL_RUN=self.run,MU300_SIM_SLOT='1')

    def reset(self,cfun):
        (self.tmp/'radio.json').write_text(json.dumps(dict(cfun=cfun,data=0)))
        (self.tmp/'commands').write_text('')

    def test_fresh_shared_initialization_preserves_modes_and_order(self):
        for shell in self.each_shell():
            self.reset([0,0])
            r=self.script(shell,SCRIPT,**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            commands=(self.tmp/'commands').read_text().splitlines()
            writes=[s for s in commands if not s.endswith('?')]
            self.assertEqual(writes,[
                'AT+SPACTCARD=0;+SFUN=2','AT+SPACTCARD=1;+SFUN=2',
                'AT+SPACTCARD=1;+SPTESTMODEM=134,128','AT+SPACTCARD=0;+SPTESTMODEM=134,128',
                'AT+SPACTCARD=1;+SPSWDATA','AT+SPACTCARD=0;+SFUN=4','AT+SPACTCARD=1;+SFUN=4'])

    def test_already_ready_is_read_only_and_mixed_state_is_refused(self):
        for shell in self.each_shell():
            for cfun,ok in [([1,1],True),([1,0],False),([0,1],False)]:
                self.reset(cfun)
                r=self.script(shell,SCRIPT,**self.extra)
                self.assertEqual(r.returncode==0,ok,r.stderr)
                if not ok: self.assertEqual(r.returncode,4)
                self.assertNotIn('SFUN=',(self.tmp/'commands').read_text())

    def test_no_urc_reader_means_no_at_traffic(self):
        for shell in self.each_shell():
            self.reset([0,0])
            ready=self.run/'mu300-at4/urc/stty_nr3.ready'
            ready.write_text('99999999')
            r=self.script(shell,SCRIPT,**self.extra)
            self.assertNotEqual(r.returncode,0)
            self.assertEqual((self.tmp/'commands').read_text(),'')
            ready.write_text(str(os.getpid()))

    def test_saved_rf_combinations_survive_cold_and_warm_initialization(self):
        for shell in self.each_shell():
            for a in (0,1):
                for b in (0,1):
                    (self.tmp/'sim-radio-policy').write_text(f'{a} {b}\n')
                    self.reset([0,0])
                    result=self.script(shell,SCRIPT,**self.extra)
                    self.assertEqual(result.returncode,0,result.stderr)
                    expected=[1 if a else 4,1 if b else 4]
                    self.assertEqual(json.loads((self.tmp/'radio.json').read_text())['cfun'],expected)
                    commands=(self.tmp/'commands').read_text()
                    for card,enabled in enumerate((a,b)):
                        self.assertEqual(f'AT+SPACTCARD={card};+SFUN=4' in commands,bool(enabled))
                    (self.tmp/'commands').write_text('')
                    result=self.script(shell,SCRIPT,**self.extra)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertNotIn('SFUN=',(self.tmp/'commands').read_text())

    def test_warm_restart_enforces_only_the_disabled_slot(self):
        for shell in self.each_shell():
            for a,b in ((0,1),(1,0),(0,0)):
                (self.tmp/'sim-radio-policy').write_text(f'{a} {b}\n')
                self.reset([1,1])
                r=self.script(shell,SCRIPT,**self.extra)
                self.assertEqual(r.returncode,0,r.stderr)
                writes=[c for c in (self.tmp/'commands').read_text().splitlines() if not c.endswith('?')]
                self.assertEqual(writes,[f'AT+SPACTCARD={slot};+CFUN=4' for slot,on in enumerate((a,b)) if not on])

    def test_empty_slot_does_not_block_the_inserted_card(self):
        for shell in self.each_shell():
            self.reset([0,0])
            (self.tmp/'radio.json').write_text(json.dumps(dict(cfun=[0,0],data=0,present=[1])))
            r=self.script(shell,SCRIPT,**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads((self.tmp/'radio.json').read_text())['cfun'],[0,1])
            writes=[s for s in (self.tmp/'commands').read_text().splitlines() if not s.endswith('?')]
            self.assertEqual(writes,['AT+SPACTCARD=1;+SFUN=2','AT+SPACTCARD=1;+SPTESTMODEM=134,128',
                                     'AT+SPACTCARD=1;+SPSWDATA','AT+SPACTCARD=1;+SFUN=4'])

    def test_only_sim0_and_already_active_sim1(self):
        for shell in self.each_shell():
            self.reset([0,0])
            (self.tmp/'radio.json').write_text(json.dumps(dict(cfun=[0,0],data=0,present=[0])))
            r=self.script(shell,SCRIPT,**dict(self.extra,MU300_SIM_SLOT='0'))
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads((self.tmp/'radio.json').read_text())['cfun'],[1,0])
            self.assertNotIn('AT+SPACTCARD=1;+SFUN',(self.tmp/'commands').read_text())
            (self.tmp/'radio.json').write_text(json.dumps(dict(cfun=[0,1],data=1,present=[1])))
            (self.tmp/'commands').write_text('')
            r=self.script(shell,SCRIPT,**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertNotIn('SFUN=',(self.tmp/'commands').read_text())
