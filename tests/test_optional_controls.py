"""Optional features must not leak SMS content or invent platform capabilities."""
import json
from helpers import ShellTest, TOP

APP=TOP/'openwrt/luci-app-mu300'
LIB=APP/'root/usr/libexec/unisoc-modem'

class OptionalControls(ShellTest):
    def test_delivery_history_is_bounded_and_metadata_only(self):
        text=(LIB/'sms-forward').read_text()
        code=text[text.index('record_delivery() {'):text.index('add_history() {')]
        for i,shell in enumerate(self.each_shell()):
            path=self.tmp/f'history{i}'
            result=self.sh(shell,code+'''
umask 077
method=smtp DELIVER_RESULT=sent
for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32; do record_delivery sms; done
DELIVER_RESULT=delivery_failed
record_delivery test
''',HISTORY=path,smtp_password='SECRET',smtp_to='private@example.com',_body='PRIVATE SMS')
            self.assertEqual(result.returncode,0,result.stderr)
            rows=path.read_text().splitlines()
            self.assertEqual(len(rows),30)
            self.assertEqual(rows[0].split('|')[1:],['test','smtp','delivery_failed'])
            self.assertNotIn('SECRET',path.read_text())
            self.assertNotIn('PRIVATE',path.read_text())
            self.assertNotIn('@',path.read_text())
            before=path.read_bytes()
            result=self.sh(shell,code+'\nrecord_delivery sms',HISTORY=path,method='smtp',DELIVER_RESULT='private@example.com')
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(path.read_bytes(),before)

    def test_cpu_packaging_menu_and_permissions(self):
        menu=json.loads((APP/'root/usr/share/luci/menu.d/luci-app-mu300.json').read_text())
        self.assertEqual(menu['admin/modem/cpu']['action']['path'],'mu300/cpu')
        acl=json.loads((APP/'root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())['luci-app-mu300']
        self.assertIn('cpu_get',acl['read']['ubus']['mu300dash'])
        self.assertNotIn('cpu_apply',acl['read']['ubus']['mu300dash'])
        for script in ('build-openwrt-tf-magisk.sh','make-release.sh'):
            source=(TOP/'tools'/script).read_text()
            for path in ('./usr/libexec/unisoc-modem/cpu ', './usr/libexec/unisoc-modem/cpu.uc ', './etc/init.d/unisoc-cpu '):
                self.assertIn(path,source)

    def test_cpu_validation_and_no_platform_voltage_writes(self):
        source=(LIB/'cpu.uc').read_text()
        self.assertNotIn('voltage_offset',source)
        self.assertIn("import * as thermal from './cpu-thermal.uc'",source)
        self.assertIn('c.cpus!=p.cpus',source)
        self.assertIn('reverse(changed)',source)
        self.assertIn('index(p.frequencies,c.min)<0',source)
