"""Hot-path shell helpers must preserve the dashboard's JSON wire values."""
import json
import shlex
import shutil
import unittest

from helpers import ShellTest, TOP


INFO = TOP / 'openwrt' / 'luci-app-mu300' / 'root' / 'usr' / 'libexec' / 'unisoc-modem' / 'dashboard-info'


class DashboardInfo(ShellTest):
    def test_dns_reuses_both_status_snapshots(self):
        script = INFO.read_text()
        self.assertIn('wan_dns=$(wan_dns_servers "$WANJSON" "$WAN6JSON")', script)
        helper = script[script.index('wan_dns_servers() {'):script.index('\nwan_up=')]
        self.assertIn('jsonfilter -s "$snapshot"', helper)
        self.assertNotIn('ubus call', helper)
        self.assertNotIn('jarr_dns', script)

    @unittest.skipUnless(shutil.which('jsonfilter'), 'also run fixture in OpenWrt container/device')
    def test_dns_with_real_jsonfilter(self):
        for shell in self.each_shell():
            result = self.script(shell, TOP/'tests/dashboard_dns_fixture.sh', INFO)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS dashboard DNS', result.stdout)

    def station_code(self):
        script = INFO.read_text()
        helpers = script[script.index('n_or_null() {'):script.index('# ------------------------------------------------------------- temperature')]
        stations = script[script.index('station_rows() {'):script.index('LAN_LEASES=')]
        leases = self.tmp / 'leases'
        leases.write_text('9999999999 E6:7A:77:59:7E:47 192.168.77.105 Xiaomi-17-Pro *\n'
                          '9999999999 aa:bb:cc:dd:ee:ff 192.168.77.106 * *\n')
        stations = stations.replace('/tmp/dhcp.leases', str(leases))
        return helpers + '\nt3() { cat; return "${IW_RC:-0}"; }\n' + stations + '\nprintf \'{"count":%s,"clients":[%s]}\' "$W_CN" "$W_CLIST"'

    def test_mac_only_station_is_counted_without_fabricated_metrics(self):
        for shell in self.each_shell():
            result = self.sh(shell, self.station_code(),
                             stdin='Station e6:7a:77:59:7e:47 (on wlan0)\n\tcurrent time: 1791393862131 ms\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['count'], 1)
            self.assertEqual(data['clients'][0], dict(mac='e6:7a:77:59:7e:47', host='Xiaomi-17-Pro',
                             ip='192.168.77.105', signal=None, tx=None, rx=None, conn=None))

    def test_complete_station_blocks_and_deduplication(self):
        dump = ('Station E6:7A:77:59:7E:47 (on wlan0)\n\tsignal: -42 [-42] dBm\n'
                '\ttx bitrate: 866.7 MBit/s VHT-MCS 9\n\trx bitrate: 433.3 MBit/s\n'
                '\tconnected time: 125 seconds\nStation aa:bb:cc:dd:ee:ff (on wlan0)\n'
                'Station e6:7a:77:59:7e:47 (on wlan0)\nStation invalid (on wlan0)\n')
        for shell in self.each_shell():
            result = self.sh(shell, self.station_code(), stdin=dump)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['count'], 2)
            self.assertEqual(data['clients'][0]['signal'], -42)
            self.assertEqual(data['clients'][0]['tx'], '866.7 Mbit/s')
            self.assertEqual(data['clients'][0]['rx'], '433.3 Mbit/s')
            self.assertEqual(data['clients'][0]['conn'], '2 min')
            self.assertIsNone(data['clients'][1]['host'])

    def test_empty_station_table_and_query_failure_are_distinct(self):
        for shell in self.each_shell():
            for rc, device, expected in [('0', 'lo', 0), ('1', 'lo', None), ('1', 'mu300-missing-test', 0)]:
                result = self.sh(shell, self.station_code(), stdin='', IW_RC=rc, WIFI_DEVICE=device)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), dict(count=expected, clients=[]))

    def test_conntrack_prefers_scalar_and_falls_back_only_when_needed(self):
        script = INFO.read_text()
        helper = script[script.index('conntrack_count() {'):script.index('CONNS=$(conntrack_count)')]
        counter, table = self.tmp / 'counter', self.tmp / 'table'
        command = helper + '\nconntrack_count ' + shlex.quote(str(counter)) + ' ' + shlex.quote(str(table))
        for shell in self.each_shell():
            for scalar, rows, expected in [('163\n', None, '163'), ('0\n', 'x\ny\n', '0'),
                                           (None, 'x\ny\n', '2'), ('bad\n', 'x\n', '1'),
                                           (None, '', '0'), (None, None, 'null')]:
                for path, content in [(counter, scalar), (table, rows)]:
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_text(content)
                result = self.sh(shell, command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_json_string_escaping_matches_original_contract(self):
        script = INFO.read_text()
        helpers = script[script.index("CR=$(printf '\\r')"):script.index('# ------------------------------------------------------------- temperature')]
        values = ['', 'normal', 'A\\B"C', '中文热点 🛜', 'line1\nline2\rline3']
        for shell in self.each_shell():
            for value in values:
                result = self.sh(shell, helpers + '\nqs "$CASE"', CASE=value)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = (json.dumps(value.replace('\n', '').replace('\r', ''), ensure_ascii=False)
                            if value else 'null')
                self.assertEqual(result.stdout, expected)


if __name__ == '__main__':
    import unittest
    unittest.main()
