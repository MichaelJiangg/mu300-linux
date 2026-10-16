"""E5 dashboard backports must preserve the single-SIM MU300 contracts."""
import json
import shutil
import subprocess
import unittest

from helpers import TOP, ShellTest

PKG = TOP / 'openwrt/luci-app-mu300'
LIB = PKG / 'root/usr/libexec/unisoc-modem'
JS = PKG / 'htdocs/luci-static/resources'


class Refresh(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_all_quick_controls_require_confirmation(self):
        result = subprocess.run(['node', str(TOP / 'tests/dashboard_quick_controls.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_scheduler_and_counter_resets(self):
        result = subprocess.run(['node', str(TOP / 'tests/dashboard_refresh.js'),
                                 str(JS / 'mu300/refresh.js'), str(JS / 'view/mu300/locks.js')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_js_syntax(self):
        for p in JS.rglob('*.js'):
            result = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, str(p) + result.stderr)

    def test_rpc_packaging_and_safety_boundaries(self):
        rpc = (PKG / 'root/usr/libexec/rpcd/mu300dash').read_text()
        self.assertIn('"rates": { }', rpc)
        self.assertIn('"cells": { "slot": "String" }', rpc)
        self.assertIn('"$cage" -ge "$TTL"', rpc)
        self.assertIn('"$sage" -ge "$TTL_FAST"', rpc)
        rates = (LIB / 'dashboard-rates').read_text()
        self.assertNotIn('AT+', rates)
        self.assertNotIn('dashboard-info', rates)
        self.assertIn("'data_interface'", rates)
        self.assertIn("'data_device'", rates)
        for name in ('dashboard-rates', 'refresh-config', 'operator.uc'):
            self.assertTrue((LIB / name).is_file())
        for name in ('home', 'locks'):
            src = (JS / f'view/mu300/{name}.js').read_text()
            self.assertIn('unload: function()', src)
        self.assertNotIn('e5-', rates)
        self.assertNotIn('t551m', rates)

    def test_sms_styles_are_scoped_and_backend_unchanged(self):
        css = (JS / 'view/mu300/sms.css').read_text()
        self.assertIn('@container(max-width:680px)', css)
        self.assertIn('minmax(0,1fr)', css)
        self.assertIn('overflow-wrap:anywhere', css)
        self.assertIn('var(--surface', css)
        sms = (JS / 'view/mu300/sms.js').read_text()
        self.assertIn("L.resource('view/mu300/sms.css')", sms)
        self.assertEqual(sms.count('id="mud-sms-num"'), 1)
        self.assertIn('M.callSmsSend', sms)
        self.assertNotIn('callSim', sms)


class StagedCollector(ShellTest):
    def test_engineering_and_neighbors_published_before_identity(self):
        self.stub('uci', 'exit 1')
        self.stub('ucode', "printf 'null\\n'")
        self.stub('fake-at', '''
printf '%s\\n' "$*" >> "$STUBLOG/commands"
case "$*" in
  *'AT+CFUN?'*) printf '+CFUN: 1\\nOK\\n' ;;
  *'AT+CEREG?'*) printf '+CEREG: 2,1,"01","01",7\\nOK\\n' ;;
  *'AT+CESQ'*) printf '+CESQ: 99,99,255,255,30,80\\nOK\\n' ;;
  *'AT+CSCS?;+COPS?'*) cp "$MU300_DASH_DIR/sig.json" "$STUBLOG/engineering.json" ;;
  *'AT+SPENGMD=0,6,6'*) cp "$MU300_DASH_DIR/cell.json" "$STUBLOG/before-neighbors.json" ;;
  *'AT+CGEQOSRDP=1'*) cp "$MU300_DASH_DIR/cell.json" "$STUBLOG/before-qos.json" ;;
  *'AT+CNUM'*) cp "$MU300_DASH_DIR/cell.json" "$STUBLOG/before-number.json" ;;
  *) printf 'OK\\n' ;;
esac''')
        for i, shell in enumerate(self.each_shell()):
            cache = self.tmp / f'cache-{i}'
            result = self.script(shell, LIB / 'cell', 'full', MU300_AT=self.stubs / 'fake-at',
                                 MU300_DASH_IDENT_DIR=self.tmp / f'ident-{i}', MU300_DASH_DIR=cache,
                                 MU300_DASH_POOL_DIR=self.tmp / f'pool-{i}')
            self.assertEqual(result.returncode, 0, result.stderr)
            get = lambda name: json.loads((self.tmp / name).read_text())
            self.assertNotIn('partial', get('engineering.json'))
            self.assertEqual(get('engineering.json')['cfun'], 1)
            self.assertEqual(get('before-neighbors.json')['neigh_pending'], 1)
            self.assertEqual(get('before-qos.json')['neigh_pending'], 0)
            self.assertEqual(get('before-number.json')['partial'], 1)
            complete = json.loads((cache / 'cell.json').read_text())
            self.assertEqual(complete['partial'], 0)
            self.assertEqual(complete['neigh_pending'], 0)
            self.assertIn('msisdn', complete['ident'])
