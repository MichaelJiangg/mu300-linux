"""Battery percentage paths shared by the dashboard and power notifications."""
from helpers import TOP, ShellTest

LIB = TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem'


class PowerSupply(ShellTest):
    def setUp(self):
        super().setUp()
        self.root = self.tmp/'supply'
        self.root.mkdir()
        self.extra = dict(MU300_POWER_SUPPLY_DIR=self.root,
                          MU300_POWER_DEVICE='u30air',
                          MU300_POWER_LIB=LIB/'power-supply.sh')

    def supply(self, name, **values):
        path = self.root/name
        path.mkdir(exist_ok=True)
        for key, value in values.items():
            (path/key).write_text(str(value)+'\n')
        return path

    def snapshot(self, shell, **env):
        source = (LIB/'dashboard-info').read_text()
        helpers = source[source.index('rd() {'):source.index('# JSON string escaping')]
        power = source[source.index('POWER_LIB='):source.index('# ------------------------------------------------------- interface counters')]
        code = helpers+power+'\nprintf "%s|%s|%s|%s|%s|%s" "$P_PRESENT" "$P_CAP" "$P_STATUS" "$P_V" "$P_I" "$P_USB"'
        return self.sh(shell, code, **(self.extra | env))

    def notification(self, shell, **env):
        source = (LIB/'sms-forward').read_text()
        number = source[source.index('number() {'):source.index('bool() {')]
        power = source[source.index('power_read() {'):source.index('add_status() {')]
        code = f'. "{LIB}/power-supply.sh"\n'+number+power+'\npower_read; printf "%s|%s|%s" "$power_ok" "$current_percent" "$current_status"'
        return self.sh(shell, code, **(self.extra | env))

    def test_mainline_percentage_and_charger_online_reach_both_consumers(self):
        self.supply('sc27xx-fgu', type='Battery', present=1, capacity=63,
                    status='Charging', voltage_now=4200000, current_now=1000000)
        self.supply('bq256xx-charger', type='USB', online=1)
        for shell in self.each_shell():
            result = self.snapshot(shell)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '1|63|Charging|4.20|1000000|1')
            result = self.notification(shell)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '1|63|Charging')

    def test_vendor_battery_is_preferred_and_zero_percent_is_valid(self):
        self.supply('battery', present=1, capacity=0, status='Discharging')
        self.supply('sc27xx-fgu', present=1, capacity=63, status='Charging')
        self.supply('usb', online=0)
        for shell in self.each_shell():
            self.assertTrue(self.snapshot(shell).stdout.startswith('1|0|Discharging|'))
            self.assertEqual(self.notification(shell).stdout, '1|0|Discharging')

    def test_invalid_capacity_or_removed_battery_is_not_a_full_battery(self):
        path = self.supply('sc27xx-fgu', present=1, capacity=63, status='Full')
        for shell in self.each_shell():
            for value in ('575', '-1', 'garbage', ''):
                (path/'capacity').write_text(value+'\n')
                self.assertTrue(self.snapshot(shell).stdout.startswith('0||'))
                self.assertEqual(self.notification(shell).stdout, '0|-1|none')
            (path/'capacity').write_text('100\n')
            (path/'present').write_text('0\n')
            self.assertTrue(self.snapshot(shell).stdout.startswith('0||'))
            self.assertEqual(self.notification(shell).stdout, '0|-1|none')
            (path/'present').write_text('1\n')

    def test_batteryless_f50_and_v50_do_not_show_phantom_fgu_percentages(self):
        self.supply('sc27xx-fgu', present=1, capacity=100, status='Full')
        for shell in self.each_shell():
            for board in ('f50', 'v50'):
                self.assertTrue(self.snapshot(shell, MU300_POWER_DEVICE=board).stdout.startswith('0||'))
                self.assertEqual(self.notification(shell, MU300_POWER_DEVICE=board).stdout, '0|-1|none')

    def test_other_battery_name_and_optional_present_attribute(self):
        self.supply('actual-cell', type='Battery', capacity=81, status='Not charging')
        for shell in self.each_shell():
            self.assertTrue(self.snapshot(shell).stdout.startswith('1|81|Not charging|'))
            self.assertEqual(self.notification(shell).stdout, '1|81|Not charging')

    def test_explicit_notification_override_is_respected_without_fallback(self):
        path = self.supply('private-battery', type='Battery', capacity=42, status='Full')
        self.supply('sc27xx-fgu', present=1, capacity=100, status='Charging')
        for shell in self.each_shell():
            self.assertEqual(self.notification(shell, MU300_FORWARD_BATTERY=path).stdout, '1|42|Full')
            self.assertEqual(self.notification(shell, MU300_FORWARD_BATTERY=self.tmp/'missing').stdout, '0|-1|none')
