"""Initial ENODEV is retryable; a working owner is never reopened to probe it."""
from helpers import ShellTest, BIN


class InitialOpen(ShellTest):
    def initialization(self):
        source=(BIN/'mu300-atd').read_text()
        return source[source.index('open_tty() {'):source.index('\n# Keep the other AT channels')]

    def test_ready_fast_path_never_waits_or_reads_clock(self):
        for shell in self.each_shell():
            code=self.initialization()+'''
printf ready >&3
'''
            self.stub('stty', ':')
            self.stub('sleep', 'exit 90')
            self.stub('date', 'exit 91')
            sink=self.tmp/'sink'
            r=self.sh(shell, code, DEV=sink)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(sink.read_text(),'ready')

    def test_failed_initial_open_survives_and_retains_the_first_success(self):
        for shell in self.each_shell():
            sink=self.tmp/'late/sink'
            if sink.exists(): sink.unlink()
            if sink.parent.exists(): sink.parent.rmdir()
            code='''retries=0
sleep() { retries=$((retries+1)); mkdir -p "$STUBLOG/late"; }
stty() { :; }
'''+self.initialization()+'''
printf ready >&3
echo "retries=$retries"
'''
            r=self.sh(shell,code,DEV=sink)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(sink.read_text(),'ready')
            self.assertIn('retries=1',r.stdout)
            self.assertIn('waiting for first open',r.stderr)

    def test_permanent_failure_is_bounded_and_describes_storage_dependency(self):
        for shell in self.each_shell():
            self.stub('date', 'echo 100')
            r=self.sh(shell,self.initialization(),DEV='/proc/mu300-invalid-tty',MU300_AT_INITIAL_WAIT=0)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('check CP firmware and eMMC availability',r.stderr)
