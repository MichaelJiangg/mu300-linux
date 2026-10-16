"""AP selection is shared and quick actions cannot disable arbitrary radios."""
import re
import json
from helpers import TOP, ShellTest

APP=TOP/'openwrt/luci-app-mu300'
LIB=APP/'root/usr/libexec/unisoc-modem'


class Hotspot(ShellTest):
    def test_action_delegates_without_global_wifi_down(self):
        self.stub('uci','exit 1')
        self.stub('hotspot','printf \'{"ok":1,"op":"wifi %s"}\\n\' "$1"')
        for shell in self.each_shell():
            for state in ('on','off'):
                result=self.script(shell,LIB/'action','wifi',state,MU300_DASH_BIN=self.stubs)
                self.assertEqual(json.loads(result.stdout),{'ok':1,'op':'wifi '+state})
        text=(LIB/'action').read_text()
        self.assertNotIn('wireless.@wifi-device[0]',text)
        self.assertNotIn('wifi down',text[text.index('    wifi:on|wifi:off)'):text.index('    modem-reset:)')])

    def test_backend_errors_translated(self):
        common=(APP/'htdocs/luci-static/resources/mu300/common.js').read_text()
        for name in ('hotspot','hotspot.uc'):
            for error in re.findall(r"error:\s*'([^']+)'",(LIB/name).read_text()):
                self.assertIn("'"+error+"': [",common)

    def test_inventory_and_shared_display(self):
        for name in ('build-openwrt-tf-magisk.sh','make-release.sh'):
            source=(TOP/'tools'/name).read_text()
            self.assertIn('./usr/libexec/unisoc-modem/hotspot ',source)
            self.assertIn('./usr/libexec/unisoc-modem/hotspot.uc ',source)
        info=(LIB/'dashboard-info').read_text()
        self.assertIn('/hotspot" fields',info)
        self.assertNotIn('wireless.radio0.',info)
