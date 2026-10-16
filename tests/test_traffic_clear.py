"""RPC/ACL/packaging contract; ledger behavior is in traffic_{core,service}.uc."""
import json
from helpers import TOP, ShellTest

PKG = TOP / 'openwrt/luci-app-mu300'
RPC = PKG / 'root/usr/libexec/rpcd/mu300dash'


class TrafficClear(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('uci', 'exit 1')
        self.stub('jsonfilter', '''
input=$(cat)
[ "$2" = '@.slot' ] && exit 0
case "$input" in *'"confirm":true'*) printf 'true\\n' ;; *) printf 'false\\n' ;; esac
''')
        self.stub('ubus', '''
printf '%s\\n' "$@" > "$STUBLOG/args"
printf '{"ok":0,"error":"confirmation_required"}\\n'
''')

    def test_rpc_contract_and_confirmation_passthrough(self):
        for shell in self.each_shell():
            methods = self.script(shell, RPC, 'list', stdin='')
            self.assertEqual(methods.returncode, 0, methods.stderr)
            self.assertEqual(json.loads(methods.stdout)['traffic_clear'], {'confirm': False, 'slot': 'String'})
            for payload in ('{}', '{"confirm":false}', '{"confirm":true}',
                            '{"confirm":true,"ubus_rpc_session":"test-session"}'):
                result = self.script(shell, RPC, 'call', 'traffic_clear', stdin=payload)
                self.assertEqual(json.loads(result.stdout)['error'], 'confirmation_required')
                expected = '{"confirm":true,"slot":0}' if '"confirm":true' in payload else '{"confirm":false,"slot":0}'
                self.assertEqual((self.tmp/'args').read_text().splitlines(),
                                 ['-t', '5', 'call', 'unisoc.traffic', 'clear', expected])

    def test_clear_requires_write_acl(self):
        acl = json.loads((PKG/'root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())['luci-app-mu300']
        read = acl['read']['ubus']['mu300dash']
        self.assertIn('traffic_get', read)
        self.assertNotIn('*', read)
        self.assertNotIn('traffic_clear', read)
        self.assertIn('*', acl['write']['ubus']['mu300dash'])

    def test_packaging_includes_service_and_view(self):
        for script in ('build-openwrt-tf-magisk.sh', 'make-release.sh'):
            text = (TOP/'tools'/script).read_text()
            for path in ('usr/libexec/unisoc-modem/traffic', 'usr/libexec/unisoc-modem/traffic-core.uc',
                         'www/luci-static/resources/view/mu300/traffic.js', 'etc/init.d/unisoc-traffic'):
                self.assertIn('./' + path, text)
