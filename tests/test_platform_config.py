"""Board migration precedes modem ownership, and keeps later user settings."""
from helpers import ShellTest, TOP

SCRIPT = TOP/'rootfs/overlay/opt/mu300/bin/mu300-platform-config'

class PlatformConfig(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('mu300-device', 'echo "$TEST_DEVICE"')
        self.stub('uci', '''
if [ "$2" = get ]; then
 case "$3" in
 unisoc_modem.main) echo core ;;
 *.u30_native_version) echo "${TEST_NATIVE_VERSION:-1}" ;;
 *.platform_defaults) echo "${TEST_DEFAULTS:-}" ;;
 *.data_sim) echo "${TEST_DATA_SIM-0}" ;;
 *.sim_slots) echo "${TEST_SLOTS:-1}" ;;
 network.wan.sim_slot) echo "${TEST_LEGACY_SLOT:-}" ;;
 esac
elif [ "$2" = batch ]; then cat > "$STUBLOG/batch"
elif [ "$2" = set ] || [ "$2" = commit ]; then echo "$*" >> "$STUBLOG/direct"; fi
''')

    def test_initial_defaults_and_same_board_preferences(self):
        for shell in self.each_shell():
            for device, marker, changes in [('v50','',True),('v50','v50',False),('f50','',True),
                                             ('u30air','',True),('f50','f50',False),('u30air','u30air',False)]:
                batch=self.tmp/'batch'; batch.unlink(missing_ok=True)
                r=self.script(shell,SCRIPT,TEST_DEVICE=device,TEST_DEFAULTS=marker)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertEqual(batch.exists(),changes)
                if changes:
                    commands=batch.read_text()
                    self.assertIn("platform_defaults='"+device+"'",commands)
                    if device in ('v50','u30air'):self.assertIn("sim_slots='2'",commands)
                    else:self.assertNotIn('sim_slots=',commands)
                    self.assertNotIn('data_sim=',commands)

    def test_selected_f50_internal_card_enables_owners_before_boot(self):
        for shell in self.each_shell():
            direct=self.tmp/'direct';direct.unlink(missing_ok=True)
            r=self.script(shell,SCRIPT,TEST_DEVICE='f50',TEST_DEFAULTS='f50',TEST_DATA_SIM='1')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('sim_slots=2',direct.read_text())
            self.assertNotIn('data_sim=',direct.read_text())

    def test_legacy_f50_selection_migrates_only_before_current_board_defaults(self):
        for shell in self.each_shell():
            direct=self.tmp/'direct';direct.unlink(missing_ok=True)
            r=self.script(shell,SCRIPT,TEST_DEVICE='f50',TEST_LEGACY_SLOT='1',TEST_DATA_SIM='')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('data_sim=1',direct.read_text())
            self.assertIn('sim_slots=2',direct.read_text())
            direct.unlink()
            r=self.script(shell,SCRIPT,TEST_DEVICE='f50',TEST_DEFAULTS='f50',TEST_LEGACY_SLOT='1')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertFalse(direct.exists())

    def test_current_selection_wins_over_stale_legacy_setting(self):
        for shell in self.each_shell():
            direct=self.tmp/'direct';direct.unlink(missing_ok=True)
            r=self.script(shell,SCRIPT,TEST_DEVICE='f50',TEST_LEGACY_SLOT='1',TEST_DATA_SIM='0')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertFalse(direct.exists())

    def test_cross_board_restore_resets_only_adapter_configuration(self):
        for shell in self.each_shell():
            for device,marker,slots in [('f50','v50',1),('u30air','v50',2),('v50','f50',2),('f50','u30air',1)]:
                batch=self.tmp/'batch';batch.unlink(missing_ok=True)
                r=self.script(shell,SCRIPT,TEST_DEVICE=device,TEST_DEFAULTS=marker)
                self.assertEqual(r.returncode,0,r.stderr)
                commands=batch.read_text()
                self.assertIn(f"sim_slots='{slots}'",commands)
                self.assertIn("data_sim='0'",commands)
                for key in ('data_sim_command','sim0_device','sim1_device'):
                    self.assertIn(f"{key}=''",commands)
                self.assertNotIn('delete ',commands)
                self.assertNotIn('network.',commands)
                self.assertNotIn('sms',commands)
                self.assertNotIn('traffic',commands)

    def test_failed_save_is_reported(self):
        self.stub('uci','case "$2" in get) [ "$3" != unisoc_modem.main ] || echo core ;; batch) cat >/dev/null; exit 1 ;; esac')
        for shell in self.each_shell():
            self.assertNotEqual(self.script(shell,SCRIPT,TEST_DEVICE='v50').returncode,0)

    def test_at_owners_start_after_platform_defaults(self):
        source=(TOP/'openwrt/overlay/etc/init.d/mu300-atd').read_text()
        self.assertLess(source.index('/mu300-platform-config'),source.index('procd_open_instance atd'))
        for file in ['tools/build-openwrt-tf-magisk.sh','tools/make-release.sh','openwrt/build-rootfs.sh']:
            self.assertIn('mu300-platform-config',(TOP/file).read_text())

    def test_existing_u30_profile_gets_capability_once_without_changing_data_sim(self):
        for shell in self.each_shell():
            commands=self.tmp/'direct';commands.unlink(missing_ok=True)
            r=self.script(shell,SCRIPT,TEST_DEVICE='u30air',TEST_DEFAULTS='u30air',TEST_NATIVE_VERSION='0')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('sim_slots=2',commands.read_text())
            self.assertNotIn('data_sim=',commands.read_text())
            commands.unlink()
            self.assertEqual(self.script(shell,SCRIPT,TEST_DEVICE='u30air',TEST_DEFAULTS='u30air').returncode,0)
            self.assertFalse(commands.exists())
