"""Actual PDU spool/import/RPC and shared pool selection, with no modem or HTTP."""
import json
from pathlib import Path
from helpers import ShellTest, TOP, BIN

LIB=TOP/'rootfs/overlay/opt/mu300/lib/sms-pool.sh'
DASH=TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem'
RPC=DASH.parent/'rpcd/mu300dash'

class SmsPoolRpc(ShellTest):
    def setUp(self):
        super().setUp()
        self.current=self.tmp/'native_pool';self.legacy=self.tmp/'old_pool'
        for p in (self.current,self.legacy): (p/'msg').mkdir(parents=True)
        self.saved=self.legacy/'msg/000009';self.saved.write_text('old sent message, keep me')
        self.lib=self.tmp/'sms-pool.sh'
        self.lib.write_text(LIB.read_text().replace('/etc/unisoc-modem/sms',str(self.legacy)).replace('/etc/mu300/sms',str(self.current)))
        self.stub('uci', '''case "$*" in
 *main.sms_pool) printf '%s\n' "${TEST_CONFIG_POOL:-}" ;;
 *main.sms_command) printf '%s\n' "${TEST_SMS_COMMAND:-}" ;;
 *main.sim_slots) echo 2 ;;
 *) exit 1 ;;
esac''')
        self.stub('jsonfilter', '''exec python3 -c 'import json,sys;x=json.load(sys.stdin);print(x.get(sys.argv[1][2:],""))' "$2"''')
        self.extra=dict(MU300_SMS_POOL_LIB=self.lib,TEST_CONFIG_POOL=self.legacy,
                        MU300_SMS_BIN=BIN/'mu300-sms',MU300_DASH_BIN=DASH,
                        MU300_DASH_DIR=self.tmp/'dash',MU300_SMS_OP_LOCK=self.tmp/'operation.lock',
                        MU300_SMS_PDU_AWK=BIN.parent/'lib/sms-pdu.awk',MU300_SMS_POOL='',MU300_SIM_SLOT='')

    def call(self,shell,slot=0):
        r=self.script(shell,RPC,'call','sms_list',stdin=json.dumps(dict(page='1',slot=str(slot))),**self.extra)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        return json.loads(r.stdout)

    def receive(self,shell,slot=0):
        env=dict(self.extra)
        if slot: env['MU300_SMS_POOL']=str(self.current/'sim1')
        raw='00040481214300006201702143652305E8329BFD06'
        result=self.script(shell,BIN/'mu300-cmt-spool',stdin='+CMT: ,20\n'+raw+'\n',**env)
        self.assertEqual(result.returncode,0,result.stderr)
        pool=self.current/('sim1' if slot else '')
        ready=next((pool/'incoming').glob('*.ready'))
        result=self.script(shell,BIN/'mu300-sms','import-pdu',ready,**env)
        self.assertEqual(result.returncode,0,result.stderr)
        return pool

    def test_two_existing_pools_direct_receive_unread_show_and_sim_isolation(self):
        for shell in self.shells:
            self.receive(shell)
            rows=self.call(shell)
            self.assertEqual((rows['total'],rows['unread']),(1,1))
            self.assertEqual(rows['msgs'][0]['time'],'2026-10-07 12:34:56+08:00')
            self.assertEqual(rows['msgs'][0]['preview'],'hello')
            self.assertEqual(rows['msgs'][0]['peer'],'1234')
            self.assertEqual(self.call(shell,1)['total'],0)
            self.receive(shell,1)
            self.assertEqual(self.call(shell,1)['msgs'][0]['preview'],'hello')
            shown=self.script(shell,RPC,'call','sms_show',stdin='{"slot":"0","id":"1"}',**self.extra)
            self.assertTrue(json.loads(shown.stdout)['ok'],shown.stderr)
            self.assertEqual(self.call(shell)['unread'],0)
            self.assertEqual(self.call(shell,1)['unread'],1)
            self.assertEqual(self.saved.read_text(),'old sent message, keep me')
            import shutil
            shutil.rmtree(self.current);(self.current/'msg').mkdir(parents=True)

    def test_time_widths_quotes_tabs_utf8_and_long_sender_do_not_shift_preview(self):
        for shell in self.shells:
            for stamp in ('2026-10-01 12:34:56+08:00','2026-10-01 12:34:56-03:30',
                          '26/10/01,12:34:56+32','2026-10-01 12:34:56','?'):
                f=self.current/'msg/000001'
                f.write_text('dir: mt\nstatus: unread\nfrom: 12345678901234567890123\nscts: '+stamp+'\n\n中文 "quote" \\path\tpreview\x01\n')
                row=self.call(shell)['msgs'][0]
                self.assertEqual(row['time'],stamp)
                self.assertEqual(row['peer'],'123456789012345678')
                self.assertEqual(row['preview'],'中文 "quote" \\path\tpreview\x01')
            f.unlink()

    def test_shared_resolver_preserves_explicit_and_custom_adapters(self):
        for shell in self.shells:
            for mode,config,command,override,expected in [
                ('native','', '', '',self.current),
                ('native',self.legacy,'','',self.current),
                ('native',self.tmp/'custom','', '',self.tmp/'custom'),
                ('adapter',self.legacy,'/custom/sms','',self.legacy),
                ('adapter',self.legacy,'/custom/sms',self.tmp/'override',self.tmp/'override')]:
                env=dict(self.extra,TEST_CONFIG_POOL=config,MU300_SMS_BIN=command,MU300_SMS_POOL=override)
                r=self.sh(shell,'. "$MU300_SMS_POOL_LIB"; mu300_sms_pool '+mode,**env)
                self.assertEqual(r.stdout.strip(),str(expected),r.stderr)

    def test_forwarding_uses_the_same_root_without_directory_existence_fallback(self):
        source=(DASH/'sms-forward').read_text()
        selection=source[source.index('BASE=${'):source.index('CONFIG=$BASE/')]
        for shell in self.shells:
            for configured,expected in [(self.legacy,self.current),(self.tmp/'custom',self.tmp/'custom')]:
                r=self.sh(shell,selection+'\nprintf "%s\\n" "$ROOT_POOL"',**dict(self.extra,TEST_CONFIG_POOL=configured))
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual(r.stdout.strip(),str(expected))

    def test_init_pool_environment_matches_for_both_sms_receivers_and_at_owners(self):
        for shell in self.shells:
            for configured,expected in [(self.legacy,self.current),(self.tmp/'custom dir',self.tmp/'custom dir')]:
                for init,entry in [('mu300-atd','start_legacy'),('mu300-smsd','start_service')]:
                    source=(TOP/'openwrt/overlay/etc/init.d'/init).read_text()
                    source=source.replace('/dev/stty_nr1','/dev/null')
                    code=source+'''\nprocd_open_instance() { instance=$1; }
procd_close_instance() { :; }
procd_set_param() {
 [ "$1" != env ] || for arg in "$@"; do
  case $arg in MU300_SMS_POOL=*) printf '%s|%s\n' "$instance" "${arg#*=}" ;; esac
 done
}
'''+entry
                    r=self.sh(shell,code,**dict(self.extra,TEST_CONFIG_POOL=configured))
                    self.assertEqual(r.returncode,0,r.stderr)
                    values=dict(line.split('|',1) for line in r.stdout.splitlines() if '|' in line)
                    pair=('atd','atd4') if init=='mu300-atd' else ('smsd','smsd-sim1')
                    self.assertEqual(values[pair[0]],str(expected))
                    self.assertEqual(values[pair[1]],str(expected/'sim1'))
