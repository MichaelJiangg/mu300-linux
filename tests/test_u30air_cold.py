"""SIM2 boot gates with fake AT brokers; no modem devices or host /run writes. The cold start, its warm-up wrapper
(the fallback to SIM1 when it cannot be done, the first-data check of a second card) and init.d/mu300-atd's dual-SIM
path, on macOS too."""
import os
import subprocess
import time
import unittest

from helpers import BIN, TOP, ShellTest


class Sim2ColdStart(ShellTest):
    def setUp(self):
        super().setUp()
        self.run = self.tmp / 'run'
        self.etc = self.tmp / 'etc'
        self.etc.mkdir()
        (self.etc / 'openwrt_release').touch()
        (self.run / 'mu300').mkdir(parents=True)
        (self.run / 'mu300-radio-freeze').touch()
        for name in ('mu300-at', 'mu300-at2', 'mu300-at4', 'mu300-at5'):
            d = self.run / name
            (d / 'owner').mkdir(parents=True)
            (d / 'owner/pid').write_text(str(os.getpid()))
            os.mkfifo(d / 'cmd')
        urc = self.run / 'mu300-at/urc'
        urc.mkdir()
        (urc / 'stty_nr0.log').write_text('CP ready\n')
        self.stub('mu300-device', 'echo "${T_DEVICE-u30air}"')
        # network.wan options other than the two the selector writes: files named uci-<option>, absent = unset
        self.stub('uci', r'''case "$*" in
 '-q get unisoc_modem.main.data_sim') cat "$STUBLOG/etc/uci-slot";;
 '-q get unisoc_modem.main.u30_sim_hot') cat "$STUBLOG/etc/uci-hot";;
 '-q get network.wan.'*) cat "$STUBLOG/etc/uci-${3#network.wan.}" 2>/dev/null;;
 'set unisoc_modem.main.data_sim='*) [ ! -e "$STUBLOG/uci-readonly" ] || exit 1; printf '%s\n' "${2#*=}" > "$STUBLOG/etc/uci-slot";;
 'set unisoc_modem.main.u30_sim_hot='*) [ ! -e "$STUBLOG/uci-readonly" ] || exit 1; printf '%s\n' "${2#*=}" > "$STUBLOG/etc/uci-hot";;
 'commit unisoc_modem') :;;
 *) exit 1;;
esac''')
        self.stub('sleep', ':')
        self.stub('sync', ':')
        self.stub('logger', 'echo "$*" >> "$STUBLOG/logger"')
        # the restart into SIM1: recorded, never the host's own reboot
        self.stub('reboot', 'echo reboot >> "$STUBLOG/reboot"')
        self.stub('setsid', 'exec "$@"')
        self.stub('ubus', r'''case "$*" in *network.interface.wan*)
    if [ -e "$STUBLOG/wan-up" ]; then printf '{ "up": true, "autostart": true, "l3_device": "%s", "ipv4-address": [ { "address": "10.0.0.2" } ] }\n' "$(cat "$STUBLOG/wan-up")"
    elif [ -e "$STUBLOG/wan-held-down" ]; then printf '{ "up": false, "autostart": false, "ipv4-address": [ ] }\n'
    else printf '{ "up": false, "autostart": true, "ipv4-address": [ ] }\n'; fi ;;
esac''')
        # The modem as our U30 Air answered (docs/FINDINGS.md 74). T_UNPOWERED=1: the card's SIM power is off at
        # boot ("+CME ERROR: 10" until AT+SPACTCARD=<n>;+SFUN=2); T_NOCARD=1: nothing answers in the position at
        # all; T_PIN: what the card says of itself; T_MODES: the work modes; T_ROUTE: what AT+SPSWDATA? answers
        # (default: the card the route was given to; "none": the question is not answered).
        self.stub('mu300-at', r'''
shift 2
echo "${MU300_AT_DIR##*/} $1" >> "$STUBLOG/at"
case $MU300_AT_DIR in *at4|*at5) slot=1;; *) slot=0;; esac
case $1 in
  'AT+CFUN?')
    if [ "${T_ALREADY_ON:-0}" = 1 ] || [ -e "$STUBLOG/radio-on" ]; then
      echo '+CFUN: 1'
    else echo '+CFUN: 0'; fi ;;
  'AT+CPIN?')
    if [ "${T_NOCARD:-0}" = 1 ] || { [ "${T_UNPOWERED:-0}" = 1 ] && [ ! -e "$STUBLOG/sim-power" ]; }; then
      echo '+CME ERROR: 10'; exit 0
    fi
    echo "+CPIN: ${T_PIN:-READY}" ;;
  'AT+SPACTCARD='[01]';+SFUN=2') touch "$STUBLOG/sim-power" ;;
  'AT+SPACTCARD='[01]';+SFUN=3') rm -f "$STUBLOG/sim-power" ;;
  'AT+CCID') echo '+CCID: 00000000000000000001' ;;
  'AT+SPTESTMODE?') [ "${T_MODES-134,134,0,19,3,1}" = none ] && { echo ERROR; exit 0; }; echo "+SPTESTMODE: ${T_MODES-134,134,0,19,3,1}" ;;
  'AT+SPSWDATA') echo "$slot" > "$STUBLOG/route" ;;
  'AT+SPSWDATA?')
    case ${T_ROUTE:-} in none) echo ERROR; exit 0 ;; '') echo "+SPSWDATA: $(cat "$STUBLOG/route" 2>/dev/null || echo 0)" ;; *) echo "+SPSWDATA: $T_ROUTE" ;; esac ;;
  'AT+SFUN=4') [ "${T_FAIL_SFUN:-0}" = 1 ] && { echo ERROR; exit 0; }; touch "$STUBLOG/radio-on" ;;
  'AT+CEREG?') echo "+CEREG: 2,${T_REG:-1}" ;;
esac
echo OK
''')
        # mobile-data: radio-locked runs the command; radio-on (the SIM1 warm-up) is only recorded
        self.stub('mobile-data', 'case $1 in radio-locked) shift; exec "$@" ;; *) echo "$*" >> "$STUBLOG/md" ;; esac')
        # init.d/mu300-atd restart, when the warm-up starts the AT service over for SIM1: recorded
        self.stub('atd-init', 'echo "$*" >> "$STUBLOG/atd-init"')
        self.start = self.copy_script('mu300-sim2-start')

    def env(self, **extra):
        extra.setdefault('MU300_SIM_ROOT', self.tmp)
        extra.setdefault('MU300_DEVICE_CMD', self.stubs / 'mu300-device')
        extra.setdefault('MU300_SIM_CONFIG_LIB', TOP / 'rootfs/overlay/opt/mu300/lib/sim-config.sh')
        extra.setdefault('MU300_REBOOT_CMD', self.stubs / 'reboot')
        extra.setdefault('MU300_SIM_REBOOT_AFTER', '0')
        extra.setdefault('MU300_ATD_INIT', self.stubs / 'atd-init')
        return super().env(**extra)

    def reason(self):
        p = self.run / 'mu300/sim2-cold-start.reason'
        return p.read_text().strip() if p.exists() else None

    def copy_script(self, name):
        p = self.tmp / name
        p.write_text((BIN / name).read_text().replace('/run/', str(self.run) + '/').replace('/etc/', str(self.etc) + '/')
                     .replace('/opt/mu300/bin/mu300-at', 'mu300-at').replace('/opt/mu300/bin/mobile-data', 'mobile-data')
                     .replace('/opt/mu300/bin/mu300-sim2-start', str(self.tmp / 'mu300-sim2-start'))
                     .replace('/usr/libexec/unisoc-modem',str(self.tmp/'plugin')))
        return p

    def boot(self, **env):
        return self.script(['bash'], self.start, '--cold-start', **env)

    def calls(self):
        p = self.tmp / 'at'
        return p.read_text().splitlines() if p.exists() else []

    def test_cold_helpers_refuse_unverified_devices_and_other_systems(self):
        for device in ('f50', 'u30pro', 'm3', ''):
            with self.subTest(device=device):
                self.assertNotEqual(self.boot(T_DEVICE=device).returncode, 0)
                self.assertFalse(self.calls())
        (self.etc / 'openwrt_release').unlink()
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertFalse(self.calls())

    def test_success_and_zero_byte_marker(self):
        r = self.boot()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), [
            'mu300-at AT+SMMSWAP=0', 'mu300-at AT+CFUN?', 'mu300-at4 AT+CFUN?',
            'mu300-at4 AT+CPIN?', 'mu300-at4 AT+CCID', 'mu300-at AT+SPTESTMODE?',
            'mu300-at5 AT+SPTESTMODEM=134,134', 'mu300-at5 AT+SPSWDATA', 'mu300-at4 AT+SPSWDATA?',
            'mu300-at5 AT+SFUN=4', 'mu300-at4 AT+CFUN?'])
        self.assertEqual((self.run / 'mu300/sim2-radio-ready').stat().st_size, 0)
        self.assertTrue((self.run / 'mu300/sim-radio-ready').exists())
        self.assertTrue((self.run / 'mu300/sim2-cold-start.sent').exists())
        log = (self.run / 'mu300/sim2-cold-start.log').read_text()
        self.assertNotIn('00000000000000000001', log)
        self.assertIn('data route read back: SIM2', log)
        self.assertIsNone(self.reason())
        # the mark that makes a later plain SIM1 dial ask the modem for the data route
        self.assertTrue((self.tmp / 'etc/mu300/sim-data-route-2').exists())
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertEqual(len(self.calls()), 11, 'second attempt must send no commands')

    def test_work_modes_are_the_modems_own(self):
        # a network mode locked on the Locks page (AT+SPTESTMODE=...) is not replaced by the start (after kanoqwq's
        # mu300-dual-radio); only a modem that does not say gets the pair this firmware's RIL sends
        r = self.boot(T_MODES='6,134,0,19,3,1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('mu300-at5 AT+SPTESTMODEM=6,134', self.calls())
        for answer in ('none', '', 'x,y', '134', '99999,1;+CFUN=0'):
            with self.subTest(answer=answer):
                for f in ('at', 'radio-on', 'route'):
                    (self.tmp / f).unlink(missing_ok=True)
                for f in ('attempted', 'sent'):
                    (self.run / f'mu300/sim2-cold-start.{f}').unlink(missing_ok=True)
                r = self.boot(T_MODES=answer)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn('mu300-at5 AT+SPTESTMODEM=134,134', self.calls())
                self.assertEqual(len([c for c in self.calls() if 'SPTESTMODEM' in c]), 1)

    def test_card_whose_sim_power_is_off_is_powered_and_started(self):
        # our U30 Air's second position: "+CME ERROR: 10" at every cold boot, READY once its SIM power is on
        r = self.boot(T_UNPOWERED='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        power = calls.index('mu300-at4 AT+SPACTCARD=1;+SFUN=2')
        self.assertLess(power, calls.index('mu300-at4 AT+CCID'))
        self.assertLess(power, calls.index('mu300-at5 AT+SPTESTMODEM=134,134'))
        self.assertTrue((self.run / 'mu300/sim2-radio-ready').exists())
        self.assertNotIn('mu300-at4 AT+SPACTCARD=1;+SFUN=3', calls)

    def test_empty_position_is_left_as_it_was_found(self):
        r = self.boot(T_NOCARD='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.reason(), 'no-sim')
        calls = self.calls()
        self.assertIn('mu300-at4 AT+SPACTCARD=1;+SFUN=2', calls)
        self.assertEqual(calls[-1], 'mu300-at4 AT+SPACTCARD=1;+SFUN=3', 'the SIM power it switched on is off again')
        self.assertFalse(any('SFUN=4' in c or 'SPTESTMODEM' in c or 'SPSWDATA' in c for c in calls))
        self.assertFalse((self.run / 'mu300/sim2-cold-start.sent').exists())
        self.assertFalse((self.tmp / 'etc/mu300/sim-data-route-2').exists())

    def test_data_route_on_the_other_card_is_a_failed_start(self):
        r = self.boot(T_ROUTE='0')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.reason(), 'data-route')
        self.assertFalse(any('SFUN=4' in c for c in self.calls()))
        self.assertTrue((self.run / 'mu300/sim2-cold-start.sent').exists())

    def test_firmware_without_the_route_question_still_starts(self):
        r = self.boot(T_ROUTE='none')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.run / 'mu300/sim2-radio-ready').exists())

    def test_registration_is_not_a_boot_gate(self):
        # CFUN=1 is the radio ready, as for SIM1: a slow registration is netifd's to wait for, never a lost boot
        r = self.boot(T_REG='2')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.run / 'mu300/sim2-radio-ready').exists())
        self.assertFalse(any('CEREG' in c for c in self.calls()))

    def test_active_radio_is_not_restarted(self):
        self.assertNotEqual(self.boot(T_ALREADY_ON='1').returncode, 0)
        self.assertEqual(self.calls(), ['mu300-at AT+SMMSWAP=0', 'mu300-at AT+CFUN?'])
        self.assertFalse((self.run / 'mu300/sim2-cold-start.sent').exists())
        self.assertEqual(self.reason(), 'not-cold')

    def test_wrong_card_stops_before_radio_on(self):
        self.assertNotEqual(self.boot(MU300_EXPECT_CCID='synthetic-mismatch').returncode, 0)
        self.assertFalse(any('SFUN' in c or 'SPTESTMODEM' in c for c in self.calls()))
        self.assertFalse((self.run / 'mu300/sim2-cold-start.sent').exists())
        self.assertEqual(self.reason(), 'wrong-card')

    def test_unready_card_stops_before_radio_on(self):
        self.assertNotEqual(self.boot(T_PIN='SIM PIN').returncode, 0)
        self.assertFalse(any('SFUN' in c or 'SPTESTMODEM' in c for c in self.calls()))
        self.assertEqual(self.reason(), 'sim-pin')
        # a locked card that had to be powered first is switched off again; nothing ever enters a PIN
        for f in ('at',):
            (self.tmp / f).unlink()
        (self.run / 'mu300/sim2-cold-start.attempted').unlink()
        self.assertNotEqual(self.boot(T_PIN='SIM PIN', T_UNPOWERED='1').returncode, 0)
        self.assertEqual(self.calls()[-1], 'mu300-at4 AT+SPACTCARD=1;+SFUN=3')
        self.assertFalse(any('CPIN=' in c for c in self.calls()))

    def test_rejected_sfun_is_not_success(self):
        self.assertNotEqual(self.boot(T_FAIL_SFUN='1').returncode, 0)
        self.assertFalse((self.run / 'mu300/sim2-radio-ready').exists())
        self.assertTrue((self.run / 'mu300/sim2-cold-start.sent').exists())
        self.assertEqual(self.reason(), 'no-radio')

    def test_missing_owner_does_not_open_tty(self):
        (self.run / 'mu300-at4/owner/pid').unlink()
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertFalse(any(c.startswith('mu300-at4 ') for c in self.calls()))

    def test_missing_cp_output_sends_nothing(self):
        (self.run / 'mu300-at/urc/stty_nr0.log').write_text('')
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_sim1_cold_path_uses_its_own_data_broker(self):
        (self.tmp / 'etc/mu300').mkdir(parents=True, exist_ok=True)
        (self.tmp / 'etc/mu300/sim-data-route-2').touch()   # an earlier boot gave the route to SIM2
        r = self.boot(MU300_SIM_SLOT='0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('mu300-at2 AT+SPSWDATA', self.calls())
        self.assertFalse((self.tmp / 'etc/mu300/sim-data-route-2').exists(), 'read back as SIM1\'s: the mark goes')
        self.assertNotIn('mu300-at5 AT+SFUN=4', self.calls())
        self.assertTrue((self.run / 'mu300/sim-radio-ready').exists())

    # --- the warm-up wrapper: confirms the boot, or falls back to SIM1
    def warmup(self, **env):
        (self.run / 'mu300/sim-slot').write_text('1\n')
        (self.etc / 'uci-slot').write_text('1\n')
        (self.etc / 'uci-hot').write_text('1\n')
        (self.etc / 'mu300-sim-pending').write_text('')
        (self.run / 'mu300/sim-managed').touch()
        # the first-data wait is real seconds (300 by default): one second here unless the test says otherwise
        if not (self.etc / 'uci-sim_data_wait').exists():
            (self.etc / 'uci-sim_data_wait').write_text('1\n')
        return self.script(['bash'], self.copy_script('mu300-sim2-warmup'), **env)

    def settings(self):
        return ((self.etc / 'uci-slot').read_text(), (self.etc / 'uci-hot').read_text(),
                (self.etc / 'mu300-sim-pending').exists(),
                (self.etc / 'mu300-sim-fallback').read_text() if (self.etc / 'mu300-sim-fallback').exists() else None)

    def test_charging_boot_sends_nothing(self):
        (self.run / 'mu300/charging-boot').touch()
        self.assertEqual(self.boot().returncode, 0)
        self.assertEqual(self.warmup().returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.etc / 'mu300-sim-pending').exists(), 'the real boot confirms')

    def check(self):
        p = self.run / 'mu300/sim-boot-check'
        return p.read_text().split()[0] if p.exists() else None

    def test_warmup_confirms_the_boot(self):
        (self.tmp / 'wan-up').write_text('sipa_eth8')
        r = self.warmup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.settings(), ('1\n', '1\n', False, None))
        self.assertTrue((self.run / 'mu300/sim2-radio-ready').exists())
        self.assertFalse((self.tmp / 'md').exists())
        self.assertFalse((self.tmp / 'reboot').exists())

    def test_failed_cold_start_after_the_radio_was_told_restarts_into_sim1(self):
        # the radio was told to start SIM2 (SPTESTMODEM went out): not undone in a running modem. The settings are
        # SIM1's again and the device restarts once - a card chosen from far away must not strand the device.
        r = self.warmup(T_FAIL_SFUN='1')
        self.assertEqual(self.settings(), ('0\n', '0\n', False, 'no-radio\n'))
        self.assertFalse((self.tmp / 'md').exists(), 'no SIM1 bring-up on a radio that was told otherwise')
        self.assertEqual((self.run / 'mu300/sim-slot').read_text(), '1\n')
        self.assertEqual((self.tmp / 'reboot').read_text(), 'reboot\n')
        self.assertTrue((self.run / 'mu300/sim-active-unknown').exists(), 'nothing dials meanwhile')
        self.assertIn('restarting into SIM1', (self.tmp / 'logger').read_text())

    def test_no_automatic_restart_when_the_owner_turned_it_off(self):
        (self.etc / 'uci-sim_restart').write_text('0\n')   # network.wan.sim_restart '0'
        r = self.warmup(T_FAIL_SFUN='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.settings(), ('0\n', '0\n', False, 'no-radio\n'))
        self.assertFalse((self.tmp / 'reboot').exists())
        self.assertIn('reboot for SIM1', (self.tmp / 'logger').read_text())

    def test_settings_that_cannot_be_written_keep_the_pending_marker(self):
        # a full or read-only filesystem: the marker makes the next boot a SIM1 boot all the same (init.d/mu300-atd)
        (self.tmp / 'uci-readonly').touch()
        self.warmup(T_PIN='SIM PIN')
        self.assertEqual(self.settings()[:3], ('1\n', '1\n', True))
        self.assertEqual((self.run / 'mu300/sim-slot').read_text(), '0\n', 'this boot is SIM1\'s already')
        self.assertEqual((self.tmp / 'md').read_text(), 'radio-on\n')

    def test_second_run_in_one_boot_concludes_nothing(self):
        # /etc/init.d/mu300-atd restart by hand in a dual-SIM boot: the owners were reopened, the cold start cannot
        # be repeated. No setting is changed and nothing restarts by itself.
        (self.tmp / 'wan-up').write_text('sipa_eth8')
        self.assertEqual(self.warmup().returncode, 0)
        (self.tmp / 'at').unlink()
        r = self.warmup()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.settings()[:2], ('1\n', '1\n'))
        self.assertIsNone(self.settings()[3])
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.run / 'mu300/sim-active-unknown').exists())
        self.assertFalse((self.tmp / 'reboot').exists())

    # --- the second card's first data (3. in mu300-sim2-warmup)
    def test_first_data_is_remembered_and_never_checked_again(self):
        (self.tmp / 'wan-up').write_text('sipa_eth8')
        self.assertEqual(self.warmup().returncode, 0)
        self.assertEqual(self.check(), 'confirmed')
        seen = self.tmp / 'etc/mu300/sim-data-seen'
        self.assertEqual(seen.read_text(), '1\n')
        self.assertEqual(seen.stat().st_mode & 0o077, 0)
        # the next boot, in a tunnel: no data, and nothing is concluded from it - an outage is not the card's failure
        (self.tmp / 'wan-up').unlink()
        for f in ('attempted', 'sent'):
            (self.run / f'mu300/sim2-cold-start.{f}').unlink()
        (self.tmp / 'radio-on').unlink()
        r = self.warmup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.check(), 'confirmed')
        self.assertEqual(self.settings(), ('1\n', '1\n', False, None))
        self.assertFalse((self.tmp / 'reboot').exists())

    def test_second_card_without_data_is_given_up_for_sim1(self):
        # the card registers (the radio is up) and gets no data: issue #194's China Telecom card, or the second
        # position of our own U30 Air (emergency service only). Measured there: back on SIM1 with data, by itself.
        (self.etc / 'uci-sim_data_wait').write_text('1\n')
        r = self.warmup()
        self.assertEqual(self.settings(), ('0\n', '0\n', False, 'no-data\n'))
        self.assertEqual(self.check(), 'failed')
        self.assertEqual((self.tmp / 'reboot').read_text(), 'reboot\n')
        self.assertFalse((self.tmp / 'etc/mu300/sim-data-seen').exists())
        self.assertIn('no mobile data', (self.tmp / 'logger').read_text())

    def test_a_failed_dials_own_teardown_is_not_a_connection_taken_down(self):
        # every failed dial of netifd's goes through a teardown, and mobile-data's "down" marker is there for a
        # moment: measured on the U30 Air, a check that looked in that moment kept a card without data. Only
        # netifd's own word (autostart false) says that somebody took the wan down.
        (self.etc / 'uci-sim_data_wait').write_text('1\n')
        (self.run / 'mu300-mobile-data-down').touch()
        self.warmup()
        self.assertEqual(self.settings()[3], 'no-data\n')
        self.assertEqual(self.check(), 'failed')

    def test_data_on_the_wrong_bearer_is_not_the_second_cards_data(self):
        (self.etc / 'uci-sim_data_wait').write_text('1\n')
        (self.tmp / 'wan-up').write_text('sipa_eth0')
        self.warmup()
        self.assertEqual(self.settings()[3], 'no-data\n')

    def test_data_check_can_be_turned_off(self):
        (self.etc / 'uci-sim_data_wait').write_text('0\n')   # "keep my choice whatever happens"
        r = self.warmup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.check(), 'off')
        self.assertEqual(self.settings(), ('1\n', '1\n', False, None))
        self.assertFalse((self.tmp / 'reboot').exists())

    def test_no_verdict_while_the_connection_is_off(self):
        (self.etc / 'uci-sim_data_wait').write_text('1\n')
        for how in ('down', 'suspend', 'auto', 'disabled'):
            with self.subTest(how=how):
                for f in ('at', 'radio-on', 'route'):
                    (self.tmp / f).unlink(missing_ok=True)
                for f in ('attempted', 'sent'):
                    (self.run / f'mu300/sim2-cold-start.{f}').unlink(missing_ok=True)
                for f in (self.tmp / 'wan-held-down', self.run / 'mu300-mobile-data.suspend',
                          self.etc / 'uci-auto', self.etc / 'uci-disabled'):
                    f.unlink(missing_ok=True)
                if how == 'down': (self.tmp / 'wan-held-down').touch()                 # ifdown wan by hand
                elif how == 'suspend': (self.run / 'mu300-mobile-data.suspend').write_text('off\n')   # mu300-power
                elif how == 'auto': (self.etc / 'uci-auto').write_text('0\n')
                else: (self.etc / 'uci-disabled').write_text('1\n')
                r = self.warmup()
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.check(), 'kept')
                self.assertEqual(self.settings(), ('1\n', '1\n', False, None))
                self.assertFalse((self.tmp / 'reboot').exists())

    def test_data_wait_setting(self):
        lib = TOP / 'rootfs/overlay/opt/mu300/lib/sim-config.sh'
        for value, want in ((None, '300'), ('0', '0'), ('45', '45'), ('', '300'), ('soon', '300'), ('-5', '300'),
                            ('999999', '300'), ('30; reboot', '300')):
            with self.subTest(value=value):
                f = self.etc / 'uci-sim_data_wait'
                f.unlink(missing_ok=True)
                if value is not None:
                    f.write_text(value + '\n')
                r = self.sh(['sh'], f'. "{lib}"; sim_cfg_data_wait', MU300_SIM_ROOT=self.tmp)
                self.assertEqual(r.stdout.strip(), want, r.stderr)
        self.assertFalse((self.tmp / 'reboot').exists())

    def test_no_data_check_for_sim1(self):
        # SIM1 chosen with live switching: it is what the device falls back to, never from
        (self.etc / 'uci-sim_data_wait').write_text('1\n')
        (self.run / 'mu300/sim-slot').write_text('0\n')
        (self.etc / 'uci-slot').write_text('0\n')
        (self.etc / 'uci-hot').write_text('1\n')
        (self.etc / 'mu300-sim-pending').write_text('')
        r = self.script(['bash'], self.copy_script('mu300-sim2-warmup'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(self.check())
        self.assertEqual(self.settings(), ('0\n', '1\n', False, None))
        self.assertFalse((self.tmp / 'reboot').exists())

    def test_cold_start_refused_before_any_command_falls_back_in_this_boot(self):
        (self.etc / 'mu300').mkdir()
        for case in ('pin', 'ccid'):
            with self.subTest(case=case):
                for p in ('at', 'md', 'logger', 'radio-on'):
                    (self.tmp / p).unlink(missing_ok=True)
                for p in ('mu300/sim2-cold-start.attempted', 'mu300/sim2-cold-start.sent', 'mu300/sim-managed',
                          'mu300-radio-freeze'):
                    (self.run / p).unlink(missing_ok=True)
                (self.run / 'mu300-radio-freeze').touch()
                env = {'T_PIN': 'SIM PIN'} if case == 'pin' else {}
                if case == 'ccid':   # the recorded card (private file) is not the one in the slot
                    (self.etc / 'mu300/sim2-iccid').write_text('synthetic-mismatch\n')
                r = self.warmup(**env)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.settings(), ('0\n', '0\n', False, 'sim-pin\n' if case == 'pin' else 'wrong-card\n'))
                self.assertFalse(any('SFUN' in c or 'SPTESTMODEM' in c for c in self.calls()))
                # this boot: the pin becomes SIM1, the freeze goes, the usual warm-up runs
                self.assertEqual((self.run / 'mu300/sim-slot').read_text(), '0\n')
                self.assertFalse((self.run / 'mu300-radio-freeze').exists())
                self.assertFalse((self.run / 'mu300/sim-managed').exists())
                self.assertEqual((self.tmp / 'md').read_text(), 'radio-on\n')
                self.assertTrue((self.run / 'mu300/sim-fallback-boot').exists())
                self.assertFalse((self.tmp / 'reboot').exists(), 'nothing was sent: no restart is needed')

    def test_missing_brokers_fall_back_without_touching_the_radio(self):
        os.unlink(self.run / 'mu300-at5/cmd')
        r = self.warmup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.settings(), ('0\n', '0\n', False, 'brokers-missing\n'))
        self.assertEqual(self.calls(), [])
        self.assertEqual((self.tmp / 'md').read_text(), 'radio-on\n')

    def test_fifo_from_a_dead_owner_is_not_startup_readiness(self):
        # nr1 itself has no owner (the readiness wait never ended: a kernel whose /dev/sipc_sbuf reads otherwise -
        # simulated on the U30 Air: AT back at 126 s, data at 132 s, in the same boot). Nothing holds a channel, so
        # the AT service starts over as the ordinary SIM1 one, with owners that respawn.
        (self.run / 'mu300-at/owner/pid').write_text('999999999\n')
        r = self.warmup()
        self.assertEqual(self.settings(), ('0\n', '0\n', False, 'brokers-missing\n'))
        self.assertEqual(self.calls(), [])
        deadline = time.monotonic() + 5   # (started detached)
        while not (self.tmp / 'atd-init').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual((self.tmp / 'atd-init').read_text(), 'restart\n')
        self.assertFalse((self.tmp / 'md').exists(), 'no radio-on through an owner that is not there')
        self.assertEqual((self.run / 'mu300/sim-slot').read_text(), '0\n')
        self.assertTrue((self.run / 'mu300/sim-fallback-boot').exists())
        self.assertFalse((self.run / 'mu300-radio-freeze').exists())
        self.assertFalse((self.tmp / 'reboot').exists())

    def test_dead_data_owner_leaves_the_dial_to_nr1(self):
        (self.run / 'mu300-at2/owner/pid').write_text('999999999\n')
        r = self.warmup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.settings()[3], 'brokers-missing\n')
        self.assertEqual((self.tmp / 'md').read_text(), 'radio-on\n')
        self.assertFalse((self.run / 'mu300-at2/cmd').exists(), 'its stale fifo would swallow every dial command')
        self.assertFalse((self.tmp / 'atd-init').exists(), 'nr1 is held open: never closed to start over')


    def test_saved_locks_replay_after_route_before_radio_on(self):
        plugin=self.tmp/'plugin';plugin.mkdir()
        (plugin/'sim-scope.sh').write_text('sim_scope() { export MU300_SIM_SLOT=$1; }\n')
        lock=plugin/'lock'
        lock.write_text('#!/bin/sh\nprintf "replay:%s:%s\\n" "$MU300_SIM_SLOT" "$MU300_SIM_CONTROL" >> "$STUBLOG/at"\n')
        lock.chmod(0o755)
        self.start=self.copy_script('mu300-sim2-start')
        r=self.boot()
        self.assertEqual(r.returncode,0,r.stderr)
        calls=self.calls()
        self.assertLess(calls.index('mu300-at4 AT+SPSWDATA?'),calls.index('replay:1:1'))
        self.assertLess(calls.index('replay:1:1'),calls.index('mu300-at5 AT+SFUN=4'))
