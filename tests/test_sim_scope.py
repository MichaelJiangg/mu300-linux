"""SIM selection is request-local; legacy SIM-0 files are never migrated/copied."""
from helpers import ShellTest, TOP

LIB = TOP / 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem'

class SimScope(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('uci', 'case "$3" in *.sim_slots) echo "${SLOTS:-2}";; *.state_dir) echo /state/lock-state.d;; esac')

    def test_slot_one_isolated_and_idempotent(self):
        for shell in self.each_shell():
            r = self.sh(shell, f'''
. '{LIB}/sim-scope.sh'
sim_scope 1 || exit 1
sim_scope 1 || exit 2
printf '%s\n' "$MU300_SIM_SLOT" "$MU300_DASH_DIR" "$MU300_STATE_DIR" "$MU300_DASH_IDENT_DIR" "$MU300_AT_DIR"
sim_scope 0 && exit 3
exit 0
''')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines(), ['1', '/tmp/unisoc-modem/sim1',
                '/state/lock-state.d/sim1', '/state/lock-state.d/sim1/identity', '/run/mu300-at4'])

    def test_single_card_rejects_second_and_invalid_address(self):
        for shell in self.each_shell():
            for slot in ('1', '2', '../0', '-1', ''):
                r = self.sh(shell, f". '{LIB}/sim-scope.sh'; sim_scope '{slot}'", SLOTS='1')
                self.assertNotEqual(r.returncode, 0, slot)

    def test_slot_zero_preserves_legacy_paths(self):
        for shell in self.each_shell():
            r = self.sh(shell, f'''
. '{LIB}/sim-scope.sh'
sim_scope 0 || exit 1
printf '%s\n' "$MU300_DASH_DIR" "$MU300_STATE_DIR" "$MU300_AT_DIR"
''', MU300_DASH_DIR='/existing/cache', MU300_STATE_DIR='/existing/locks', MU300_AT_DIR='/run/mu300-at6')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines(), ['/existing/cache','/existing/locks','/run/mu300-at6'])

    def test_sms_commands_and_ack_are_addressed_atomically(self):
        sms=(TOP/'rootfs/overlay/opt/mu300/bin/mu300-sms').read_text()
        smsd=(TOP/'rootfs/overlay/opt/mu300/bin/mu300-smsd').read_text()
        wrapper=sms[sms.index('at() {'):sms.index('\n# ------------------------------------------------------------------ the pool')]
        ack=smsd[smsd.index('sms_at() {'):smsd.index('\n# one daemon')]
        self.stub('mu300-at', 'printf "%s" "$3"')
        for shell in self.each_shell():
            for slot in ('0','1'):
                r=self.sh(shell,wrapper+"\nat 'AT+CMGS=3\rAABBCC\032'",MU300_SIM_SLOT=slot)
                # subprocess text mode normalizes CR; byte content is otherwise unchanged.
                self.assertEqual(r.stdout,f'AT+SPACTCARD={slot};+CMGS=3\nAABBCC\x1a')
                r=self.sh(shell,ack+"\nsms_at 5 'AT+CNMA=1'",MU300_SIM_SLOT=slot)
                self.assertEqual(r.stdout,f'AT+SPACTCARD={slot};+CNMA=1')

    def test_browser_selection_follows_only_successful_data_switch(self):
        import shutil, subprocess
        if not shutil.which('node'): self.skipTest('Node required')
        r=subprocess.run(['node',str(TOP/'tests/dashboard_sim.js')],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
