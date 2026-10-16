"""Upstream 1f6db8c/7106ed9 concurrency regression tests, on a fake disk."""
import os
import shutil
import signal
import subprocess
import time
import re
from helpers import BIN, ShellTest

class Lock(ShellTest):
    """One mu300-update at a time: the second says who holds the lock and exits 1 before it touches anything.
    With flock where the machine has it (busybox's applet on OpenWrt, util-linux on Ubuntu), with a pid directory
    without; NO_FLOCK forces the directory on a machine that has flock."""
    NO_FLOCK = 'have() { [ "$1" != flock ] && command -v "$1" >/dev/null 2>&1; }'

    def setUp(self):
        super().setUp()
        # the updater makes its own directory under /run (there on both systems), never /run itself
        self.disk = self.tmp / 'disk'
        self.root = self.tmp / 'root'
        (self.tmp / 'locks').mkdir(mode=0o700)
        self.lock = self.tmp / 'locks' / 'mu300-update'
        self.holders = []

    def tearDown(self):
        self.end_holders()
        super().tearDown()

    def lock_env(self):
        return self.env(MU300_LIB=1, MU300_DISK=self.disk, MU300_BIN=BIN, MU300_SYSROOT=self.root, MU300_LOCK=self.lock)

    def hold(self, shell, prelude=':'):
        """A separate process that takes the lock and keeps it; its pid, once it has the lock."""
        mark = self.tmp / 'held'
        mark.unlink(missing_ok=True)
        # its own process group: the lock is the shell's and its children's (sleep inherits the flock descriptor), as
        # a run's is while its unpacking or download still runs - ending the holder means the whole group
        h = subprocess.Popen(shell + ['-c', f'. "{BIN}/mu300-update"; {prelude}; lock_take || exit 9; echo $$ > "{mark}"; sleep 30; :'],
                             env=self.lock_env(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
        self.holders.append(h)
        for _ in range(100):
            if mark.exists() and mark.read_text().strip():
                return int(mark.read_text())
            if h.poll() is not None:
                self.fail(f'the holder ended: {h.stderr.read()}')
            time.sleep(0.05)
        self.fail('the holder never took the lock')

    def take(self, shell, prelude=':'):
        """lock_take in a fresh process, dropped at its end as the dispatch does: (exit status, stderr, stdout)."""
        r = self.sh(shell, f'. "{BIN}/mu300-update"; {prelude}; lock_take; trap lock_drop EXIT; echo taken', MU300_LIB=1,
                    MU300_DISK=self.disk, MU300_BIN=BIN, MU300_SYSROOT=self.root, MU300_LOCK=self.lock)
        return r.returncode, r.stderr, r.stdout

    def end_holders(self):
        for h in self.holders:
            if h.poll() is None:
                os.killpg(h.pid, signal.SIGKILL)
            h.wait(); h.stderr.close()
        self.holders = []

    def check_second_run(self, shell, prelude):
        pid = self.hold(shell, prelude)
        rc, err, out = self.take(shell, prelude)
        self.assertEqual(rc, 1, err)
        self.assertEqual(err.strip(), f'another mu300-update is running (pid {pid})')
        self.assertEqual(out, '')
        # free again once the holder is gone - killed, so without its own cleanup
        self.end_holders()
        rc, err, out = self.take(shell, prelude)
        self.assertEqual((rc, out), (0, 'taken\n'), err)

    def test_inherited_flock_is_not_reopened_during_self_update(self):
        if not shutil.which('flock'):
            self.skipTest('flock required')
        for shell in self.each_shell():
            r = self.sh(shell, f'. "{BIN}/mu300-update"; lock_take; sleep 2 & child=$!; '
                        'lock_take; result=$?; kill "$child"; wait "$child" 2>/dev/null; exit "$result"',
                        MU300_LIB=1, MU300_LOCK=self.lock, MU300_DISK=self.disk)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_second_run_is_refused_with_the_holders_pid(self):
        for shell in self.each_shell():
            self.check_second_run(shell, ':')

    def test_without_flock_a_pid_directory(self):
        for shell in self.each_shell():
            self.check_second_run(shell, self.NO_FLOCK)
            d = self.lock / 'held'
            self.assertFalse(d.exists())    # lock_drop ran at the end of take
            # a directory left by a holder that is gone (a pid nothing has) is taken over, and says so
            d.mkdir(); (d / 'pid').write_text('999999\n')
            rc, err, out = self.take(shell, self.NO_FLOCK)
            self.assertEqual((rc, out), (0, 'taken\n'), err)
            self.assertIn('taking over the lock of a mu300-update that is gone (pid 999999)', err)
            self.assertFalse(d.exists())
            # what is not a pid (never run, never echoed) is a run that is gone too
            d.mkdir(); (d / 'pid').write_text('12; rm -rf / # $(reboot)\n')
            rc, err, out = self.take(shell, self.NO_FLOCK)
            self.assertEqual((rc, out), (0, 'taken\n'), err)
            self.assertIn('taking over the lock of a mu300-update that is gone\n', err)
            self.assertNotIn('rm -rf', err)
            # one with no pid at all (its holder went between making it and writing its pid) is given a second
            # to write it, then taken over too: never a denial for good
            d.mkdir()
            t = time.monotonic()
            rc, err, out = self.take(shell, self.NO_FLOCK)
            self.assertEqual((rc, err.strip(), out), (0, 'taking over the lock of a mu300-update that is gone', 'taken\n'))
            self.assertGreater(time.monotonic() - t, 0.9)
            self.assertFalse(d.exists())
            # a live process that is not a mu300-update (this test run) is a reused pid, not a holder - where
            # /proc can tell; without it (macOS) only "alive" is known, and it counts as a holder
            d.mkdir(); (d / 'pid').write_text(f'{os.getpid()}\n')
            rc, err, out = self.take(shell, self.NO_FLOCK)
            if os.path.exists('/proc/self/cmdline'):
                self.assertEqual((rc, out), (0, 'taken\n'), err)
                self.assertFalse(d.exists())
            else:
                self.assertEqual((rc, err.strip(), out), (1, f'another mu300-update is running (pid {os.getpid()})', ''))
                shutil.rmtree(d)

    def test_the_pid_file_names_the_holder_with_flock(self):
        if not shutil.which('flock'):
            self.skipTest('no flock here')
        for shell in self.each_shell():
            pid = self.hold(shell)
            self.assertEqual((self.lock / 'lock').read_text().strip(), str(pid))
            self.end_holders()
            # the file is only informative once the holder is gone: the kernel released the lock
            rc, err, out = self.take(shell)
            self.assertEqual((rc, out), (0, 'taken\n'), err)
            # a lock file that is not a regular file is refused, the run does not go on unlocked
            (self.lock / 'lock').unlink(); (self.lock / 'lock').symlink_to(self.tmp / 'elsewhere')
            rc, err, out = self.take(shell)
            self.assertEqual((rc, out), (1, ''))
            self.assertIn('is not a regular file; not running', err)
            (self.lock / 'lock').unlink()

    def test_refuses_a_lock_path_that_is_not_its_own_directory(self):
        # nothing runs unlocked: a link at the path (to anywhere), a directory anyone else can write, or one that
        # cannot be made stop the run with exit 1 before it touches anything
        elsewhere = self.tmp / 'elsewhere'
        elsewhere.mkdir(mode=0o700)
        for shell in self.each_shell():
            for prelude in (':', self.NO_FLOCK):
                shutil.rmtree(self.lock, ignore_errors=True)
                self.lock.symlink_to(elsewhere)
                rc, err, out = self.take(shell, prelude)
                self.assertEqual((rc, out), (1, ''), err)
                self.assertIn(f'cannot lock: {self.lock} is a symbolic link; not running', err)
                self.assertEqual(list(elsewhere.iterdir()), [])
                self.lock.unlink()
                self.lock.mkdir(mode=0o777)
                rc, err, out = self.take(shell, prelude)
                self.assertEqual((rc, out), (1, ''), err)
                self.assertIn('is not a directory of mode 700; not running', err)
                self.assertEqual(list(self.lock.iterdir()), [])
                self.lock.rmdir()
                self.lock.write_text('')
                rc, err, out = self.take(shell, prelude)
                self.assertEqual((rc, out), (1, ''), err)
                self.assertIn('is not a directory of mode 700; not running', err)
                self.lock.unlink()
                if os.geteuid() != 0:
                    self.lock.parent.chmod(0o500)
                    rc, err, out = self.take(shell, prelude)
                    self.lock.parent.chmod(0o700)
                    self.assertEqual((rc, out), (1, ''), err)
                    self.assertIn(f'cannot lock: cannot make {self.lock}; not running', err)
            # made by the run itself: mode 700
            rc, err, out = self.take(shell)
            self.assertEqual((rc, out), (0, 'taken\n'), err)
            self.assertEqual(self.lock.stat().st_mode & 0o777, 0o700)

    def test_what_changes_the_disk_locks_and_what_only_looks_does_not(self):
        src = (BIN / 'mu300-update').read_text()
        main = src[src.index('[ "$(id -u)" = 0 ]'):]
        m = re.search(r'^\s*([a-z|-]+)\)\n\s*lock_take;', main, re.M)
        self.assertIsNotNone(m, 'no command locks')
        self.assertEqual(set(m.group(1).split('|')), {'apply', 'boot', 'kernel', 'rollback', 'rollback-boot', 'clean', 'accounts'})
        self.assertLess(main.index('lock_take'), main.index('keepalive_start'))
        self.assertIn("lock_drop' EXIT", main)
        # under /run (root's own, so no login user can plant a link or a lock there), not in $STAGE (clean deletes
        # it) nor /tmp or /var/lock (anyone's)
        self.assertIn('LOCK=${MU300_LOCK:-/run/mu300-update}', src)
        self.assertNotIn('/var/lock/mu300-update', src)
        self.assertNotIn('going on without', src)
