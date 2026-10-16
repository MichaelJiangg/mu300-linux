"""Own-number lookup is fresh on full rounds, while static identity stays cached."""
import json
from pathlib import Path

from helpers import ShellTest, TOP


CELL = TOP / 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/cell'


class DashboardIdentity(ShellTest):
    def test_ims_uri_parsing(self):
        source = CELL.read_text(encoding='utf-8')
        helper = source[source.index('ims_number() {'):source.index('# --------------------------------------------------------------- one collector')]
        cases = [
            ('+SPPAURI: sip:+8613800000000@ims.example.org\nOK\n', '+8613800000000'),
            ('+SPPAURI: "sip:+8613800000000@ims.example.org","tel:+905551234567"\n', '+905551234567'),
            ('+SPPAURI: <tel:13800000000;phone-context=+86>\n', '13800000000'),
            ('+SPPAURI: sips:+90-555-1234567@ims.example.org;user=phone\n', '+905551234567'),
            ('+SPPAURI: sip:460011234567890@ims.example.org\n', ''),
            ('+SPPAURI: sip:alice@ims.example.org\n', ''),
            ('+SPPAURI: tel:+1234567890123456\n', ''),
            ('+SPPAURI: ""\nOK\n', ''), ('ERROR\n', ''),
        ]
        for shell in self.each_shell():
            for reply, expected in cases:
                result = self.sh(shell, helper + '\nprintf "%s" "$REPLY" | ims_number', REPLY=reply)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_cnum_parsing(self):
        source = CELL.read_text(encoding='utf-8')
        helper = source[source.index('cnum_number() {'):source.index('# --------------------------------------------------------------- one collector')]
        cases = [
            ('AT+CNUM\r\n+CNUM: "","+8613800000000",145\r\nOK\r\n', '+8613800000000'),
            ('+CNUM: "SIM, voice","8613800000000",145,,,4\nOK\n', '+8613800000000'),
            ('+CNUM: "","13800000000",129\nOK\n', '13800000000'),
            ('+CNUM: "","",129\n+CNUM: "voice","+90 555 123 4567",145\n', '+905551234567'),
            ('OK\n', ''), ('ERROR\n', ''),
            ('+CNUM: "my number","",129\n', ''),
            ('+CNUM: "","unknown",129\n', ''),
        ]
        for shell in self.each_shell():
            for reply, expected in cases:
                result = self.sh(shell, helper + '\nprintf "%s" "$REPLY" | tr -d "\\r" | cnum_number', REPLY=reply)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_empty_number_retries_without_requerying_static_identity(self):
        self.stub('uci', 'exit 1')
        self.stub('fake-at', '''printf '%s\\n' "$*" >> "$STUBLOG/at-commands"
case "$*" in
  *AT+CFUN?*) printf '+CFUN: 1\\nOK\\n' ;;
  *AT+CIMI*) printf '460011234567890\\nOK\\n' ;;
  *) printf 'OK\\n' ;;
esac''')
        for i, shell in enumerate(self.each_shell()):
            ident = self.tmp / f'ident-{i}'
            ident.mkdir()
            (ident / 'sim.json').write_text('{"imsi":"460011234567890"}')
            log = self.tmp / 'at-commands'
            log.unlink(missing_ok=True)
            env = dict(MU300_AT=self.stubs / 'fake-at', MU300_DASH_IDENT_DIR=ident,
                       MU300_DASH_DIR=self.tmp / f'cache-{i}', MU300_DASH_POOL_DIR=self.tmp / f'pool-{i}')
            for mode in ('full', 'full', 'fast'):
                result = self.script(shell, CELL, mode, **env)
                self.assertEqual(result.returncode, 0, result.stderr)
            cached = json.loads((ident / 'sim.json').read_text())
            self.assertNotIn('msisdn', cached)
            self.assertNotIn('msisdn_source', cached)
            self.assertEqual(log.read_text().count('AT+CNUM'), 2)
            self.assertEqual(log.read_text().count('AT+SPPAURI?'), 2)
            self.assertEqual(log.read_text().count('AT+CIMI'), 1)
            data = json.loads((self.tmp / f'cache-{i}' / 'cell.json').read_text())
            self.assertIsNone(data['ident']['msisdn'])

    def test_ims_fallback_and_reboot_invalidation(self):
        self.stub('uci', 'exit 1')
        self.stub('fake-at', '''printf '%s\\n' "$*" >> "$STUBLOG/at-commands"
case "$*" in
  *AT+CFUN?*) printf '+CFUN: 1\\nOK\\n' ;;
  *AT+CIMI*) printf '460011234567890\\nOK\\n' ;;
  *AT+CNUM*) printf '%s\\n' "$CNUM_REPLY" ;;
  *AT+SPPAURI?*) printf '+SPPAURI: sip:+8613800000000@ims.example.org\\nOK\\n' ;;
  *) printf 'OK\\n' ;;
esac''')
        for i, shell in enumerate(self.each_shell()):
            ident = self.tmp / f'ims-ident-{i}'
            ident.mkdir()
            cache = ident / 'sim.json'
            cache.write_text(json.dumps({'msisdn': '+905550000000', 'boot_id': 'previous-boot'}))
            log = self.tmp / 'at-commands'
            log.unlink(missing_ok=True)
            env = dict(MU300_AT=self.stubs / 'fake-at', MU300_DASH_IDENT_DIR=ident,
                       MU300_DASH_DIR=self.tmp / f'ims-cache-{i}', MU300_DASH_POOL_DIR=self.tmp / f'ims-pool-{i}',
                       CNUM_REPLY='+CME ERROR: 22')
            result = self.script(shell, CELL, 'full', **env)
            self.assertEqual(result.returncode, 0, result.stderr)
            cached = json.loads(cache.read_text())
            data = json.loads((env['MU300_DASH_DIR'] / 'cell.json').read_text())
            self.assertEqual(data['ident']['msisdn'], '+8613800000000')
            self.assertEqual(data['ident']['msisdn_source'], 'ims')
            self.assertNotIn('msisdn', cached)
            self.assertNotEqual(cached['boot_id'], 'previous-boot')
            # Same boot reuses static identity, but always queries the number.
            result = self.script(shell, CELL, 'full', **env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(log.read_text().count('AT+SPPAURI?'), 2)
            self.assertEqual(log.read_text().count('AT+CIMI'), 1)
            cached['boot_id'] = 'previous-boot'
            cache.write_text(json.dumps(cached))
            env['CNUM_REPLY'] = '+CNUM: "","+905551234567",145\nOK'
            result = self.script(shell, CELL, 'full', **env)
            self.assertEqual(result.returncode, 0, result.stderr)
            cached = json.loads(cache.read_text())
            data = json.loads((env['MU300_DASH_DIR'] / 'cell.json').read_text())
            self.assertEqual(data['ident']['msisdn'], '+905551234567')
            self.assertEqual(data['ident']['msisdn_source'], 'sim')
            self.assertNotIn('msisdn', cached)
            self.assertEqual(log.read_text().count('AT+SPPAURI?'), 2)
            self.assertEqual(log.read_text().count('AT+CIMI'), 2)

    def test_live_number_recovers_after_startup_and_never_reuses_old_value(self):
        self.stub('uci', 'exit 1')
        self.stub('fake-at', '''printf '%s\\n' "$*" >> "$STUBLOG/at-commands"
case "$*" in
  *AT+CFUN?*) printf '+CFUN: 1\\nOK\\n' ;;
  *AT+CIMI*) printf '460011234567890\\nOK\\n' ;;
  *AT+CNUM*) printf '%s\\n' "$CNUM_REPLY" ;;
  *AT+SPPAURI?*) printf '%s\\n' "$IMS_REPLY" ;;
  *) printf 'OK\\n' ;;
esac''')
        for i, shell in enumerate(self.each_shell()):
            ident = self.tmp / f'live-ident-{i}'
            ident.mkdir()
            cache = ident / 'sim.json'
            # A fresh legacy cache containing a stale number must migrate too.
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            cache.write_text(json.dumps({'msisdn': '+905550000000', 'boot_id': boot}, separators=(',', ':')))
            log = self.tmp / 'at-commands'
            log.unlink(missing_ok=True)
            env = dict(MU300_AT=self.stubs / 'fake-at', MU300_DASH_IDENT_DIR=ident,
                       MU300_DASH_DIR=self.tmp / f'live-cache-{i}', MU300_DASH_POOL_DIR=self.tmp / f'live-pool-{i}')
            previous = None
            for cnum, ims, number, source in [
                ('ERROR', 'OK', None, None),
                ('ERROR', '+SPPAURI: tel:+8613800000000\nOK', '+8613800000000', 'ims'),
                ('+CNUM: "","+905551234567",145\nOK', 'ERROR', '+905551234567', 'sim'),
                ('ERROR', 'ERROR', None, None),
            ]:
                result = self.script(shell, CELL, 'full', CNUM_REPLY=cnum, IMS_REPLY=ims, **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads((env['MU300_DASH_DIR'] / 'cell.json').read_text())
                self.assertEqual(data['ident']['msisdn'], number)
                self.assertEqual(data['ident']['msisdn_source'], source)
                self.assertNotIn('msisdn', json.loads(cache.read_text()))
                if previous is not None:
                    self.assertEqual((cache.read_bytes(), cache.stat().st_mtime_ns), previous)
                previous = (cache.read_bytes(), cache.stat().st_mtime_ns)
            self.assertEqual(log.read_text().count('AT+CIMI'), 1)
            self.assertEqual(log.read_text().count('AT+CNUM'), 4)
            self.assertEqual(log.read_text().count('AT+SPPAURI?'), 3)
