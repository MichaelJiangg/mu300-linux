"""Do not interpret query reporting mode as registration or use another SIM URC."""
from helpers import ShellTest, BIN


class RegistrationScope(ShellTest):
    def test_query_and_unsolicited_forms_do_not_overlap(self):
        source = (BIN / 'mobile-data').read_text()
        function = source[source.index('is_registered() {'):source.index('\nwait_registered()')]
        for shell in self.each_shell():
            for kind, reply, expected in [
                ('query', '+CEREG: 1,8', False),
                ('query', '+CEREG: 5,2', False),
                ('query', '+CEREG: 2,1,"F2F5","0140589A",7', True),
                ('query', '+CEREG: 2,5', True),
                ('query', '+CEREG: 2,1\n+CEREG: 2,8', False),
                ('urc', '+CEREG: 1,"F2F5","0140589A",7', True),
                ('urc', '+CEREG: 5', True),
                ('urc', '+CEREG: 8', False),
                ('urc', '+CEREG: 1\n+CEREG: 2', False),
            ]:
                r = self.sh(shell, function + '\nis_registered ' + kind, stdin=reply+'\n')
                self.assertEqual(r.returncode == 0, expected, (kind, reply, r.stderr))

    def test_wait_uses_selected_stream_and_consumes_each_batch(self):
        source = (BIN / 'mobile-data').read_text()
        function = source[source.index('wait_registered() {'):source.index('\n# The modem needs')]
        self.assertIn('urclog=${MU300_SIM_URC:-', function)
        self.assertIn('is_registered urc', function)
        self.assertIn('start=$((size + 1))\n        if', function)
        self.assertIn('[ "$((size + 1))" -lt "$start" ]', function)

    def test_procd_env_is_a_single_table_per_instance(self):
        # procd_set_param env creates an object, it does not append to one.
        from helpers import TOP
        source = (TOP / 'openwrt/overlay/etc/init.d/mu300-atd').read_text()
        code = source + '''
procd_open_instance() { instance=$1; env_count=0; }
procd_set_param() {
    [ "$1" != env ] || { env_count=$((env_count+1)); [ "$env_count" = 1 ] || exit 12; }
    if [ "$instance" = atd4 ] && [ "$1" = env ]; then printf '%s\n' "$@"; fi
}
procd_close_instance() { :; }
start_service
'''
        self.stub('uci', 'echo 2')
        for shell in self.each_shell():
            r = self.sh(shell, code)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('MU300_AT_DIR=/run/mu300-at4', r.stdout)
            self.assertIn('MU300_AT_URC_CHANNELS=3', r.stdout)
            self.assertIn('MU300_SMS_POOL=/etc/mu300/sms/sim1', r.stdout)

    def test_cancel_pending_registration_does_not_send_more_at(self):
        source=(BIN/'mobile-data').read_text()
        function=source[source.index('wait_registered() {'):source.index('\n# The modem needs')]
        flag=self.tmp/'cancelled';flag.touch()
        log=self.tmp/'urc.log';log.write_text('')
        function=function.replace('/run/mu300-mobile-data-down',str(flag))
        r=self.sh(['bash'],function+'''\nat() { echo unexpected; }
wait_registered
''', MU300_SIM_URC=log)
        self.assertEqual(r.returncode,1,r.stderr)
        self.assertEqual(r.stdout,'')
