"""The dashboard must use the modem's NR band and parse LTE neighbor blocks."""
import json

from helpers import ShellTest, TOP


CELL = TOP / 'openwrt' / 'luci-app-mu300' / 'root' / 'usr' / 'libexec' / 'unisoc-modem' / 'cell'
NR_REPLY = (
    '78,78,78,78,78,78-627264,627264,627264,627264,627264,627264-'
    '687,973,234,232,709,954--10865,-10542,-10889,-10995,-11825,-11497-'
    '-1195,-1137,-1846,-1632,-1836,-1499-336,649,-749,-456,-766,-277-'
    '32,32,32,32,32,32-1,1,1,1,1,1'
)
LTE_REPLY = (
    '1650,211,-9500,-800,0,0,0,0,0,0,0,0-'
    '46600,123,-11000,-1500,0,0,0,0,0,0,0,0'
)


class DashboardNeighbors(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('uci', 'exit 1')

    def collect(self, nr_reply, lte_reply, shell, suffix):
        self.stub('fake-at', f'''printf '%s\\n' "$*" >> "$STUBLOG/at-commands"
case "$*" in
  *AT+CFUN?*) printf '+CFUN: 1\\nOK\\n' ;;
  *AT+CEREG?*) printf '+CEREG: 2,1,"899C10","09C6D007",11\\nOK\\n' ;;
  *AT+C5GREG?*) printf '+C5GREG: 2,1,"899C10","899C6D007",11\\nOK\\n' ;;
  *AT+SPENGMD=0,6,6*) printf '%s\\nOK\\n' '{lte_reply}' ;;
  *AT+SPENGMD=0,14,2*) printf '%s\\nOK\\n' '{nr_reply}' ;;
  *AT+SPQ5GNCELLEX*) printf '+SPQ5GNCELLEX: 0,0,0,0,0,0,0,0,1,627264,687,-10830,-1100,330,0,0,0\\nOK\\n' ;;
  *) printf 'OK\\n' ;;
esac''')
        out = self.tmp / f'cache-{suffix}'
        result = self.script(
            shell, CELL, 'full', MU300_AT=self.stubs / 'fake-at',
            MU300_DASH_DIR=out, MU300_DASH_POOL_DIR=self.tmp / f'pool-{suffix}',
            MU300_DASH_IDENT_DIR=self.tmp / f'ident-{suffix}',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((out / 'cell.json').read_text())

    def test_nr_band_from_modem_and_lte_csv_blocks(self):
        for i, shell in enumerate(self.each_shell()):
            (self.tmp / 'at-commands').unlink(missing_ok=True)
            cell = self.collect(NR_REPLY, LTE_REPLY, shell, str(i))
            nr = [n for n in cell['neigh'] if n['rat'] == 'nr']
            lte = [n for n in cell['neigh'] if n['rat'] == 'lte']
            self.assertEqual(len(nr), 6)
            self.assertEqual({n['band'] for n in nr}, {78})
            self.assertEqual(nr[0]['arfcn'], 627264)
            self.assertEqual(nr[0]['sinr'], 3.4)
            self.assertEqual([(n['band'], n['arfcn'], n['pci']) for n in lte],
                             [(3, 1650, 211), (45, 46600, 123)])
            self.assertEqual(lte[0]['rsrp'], -95.0)
            commands = (self.tmp / 'at-commands').read_text()
            self.assertIn('AT+SPENGMD=0,14,2', commands)
            self.assertNotIn('AT+SPQ5GNCELLEX', commands)

    def test_nr_fallback_does_not_guess_overlapping_band(self):
        for i, shell in enumerate(self.each_shell()):
            cell = self.collect('ERROR', '', shell, f'fallback-{i}')
            nr = [n for n in cell['neigh'] if n['rat'] == 'nr']
            self.assertEqual(len(nr), 1)
            self.assertIsNone(nr[0]['band'])
            self.assertEqual(nr[0]['band_candidates'], [77, 78])
            self.assertEqual(nr[0]['arfcn'], 627264)


if __name__ == '__main__':
    import unittest
    unittest.main()
