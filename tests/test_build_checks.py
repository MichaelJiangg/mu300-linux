"""Build checks that keep an old binary out of a kernel bundle (after kanoqwq 265f4de3, f6b0668d, f0926715):
make-bundle.sh refuses a vendor module whose source changed after it was built, build-wlan.sh a Wi-Fi tree patched
with another patch set, and build-all.sh's patched_copy removes only its own copies."""
import os
import re
import time

from helpers import TOP, ShellTest

BUNDLE = TOP / 'upstream' / 'make-bundle.sh'


class StaleModules(ShellTest):
    def setUp(self):
        super().setUp()
        self.top = self.tmp / 'top'
        self.out = self.top / 'upstream' / 'out'
        (self.out / 'modules').mkdir(parents=True)
        for n in ('wcn_bsp', 'sprd_wlan_combo'):
            d = self.top / 'upstream' / 'modules' / n / 'common'
            d.mkdir(parents=True)
            (d / 'x.c').write_text('int x;\n')
        self.built()

    def built(self, n=None, ago=0):
        """the build logs, written after every source (as build-modules.sh does), AGO seconds back"""
        t = time.time() - ago
        for d in (self.top / 'upstream' / 'modules').iterdir():
            if n in (None, d.name):
                log = self.out / 'modules' / (d.name + '.log')
                log.write_text('make ...\n')
                os.utime(log, (t, t))

    def check(self, shell):
        m = re.search(r'# --- stale begin\n(.*?)# --- stale end', BUNDLE.read_text(), re.S)
        self.assertIsNotNone(m, 'make-bundle.sh has no stale block')
        code = f'TOP="{self.top}" U="{self.top}/upstream" UO="{self.out}" krel=6.18.58-mu300\n' + m.group(1) + 'echo fine\n'
        return self.sh(shell, code)

    def test_fresh_build_passes(self):
        for shell in self.each_shell():
            self.built(ago=0)
            for f in self.top.glob('upstream/modules/*/common/x.c'):
                os.utime(f, (time.time() - 60, time.time() - 60))
            r = self.check(shell)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'fine'), r.stderr)

    def test_a_source_changed_after_the_build_is_refused(self):
        for shell in self.each_shell():
            self.built(ago=60)
            src = self.top / 'upstream' / 'modules' / 'sprd_wlan_combo' / 'common' / 'x.c'
            os.utime(src, None)
            r = self.check(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn('upstream/modules/sprd_wlan_combo/common/x.c changed after sprd_wlan_combo was built', r.stderr)
            self.assertIn('build-modules.sh sprd_wlan_combo', r.stderr)

    def test_a_module_never_built_is_refused(self):
        for shell in self.each_shell():
            (self.out / 'modules' / 'wcn_bsp.log').unlink(missing_ok=True)
            r = self.check(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn('wcn_bsp was not built for this kernel', r.stderr)
            self.built('wcn_bsp')


class WlanPatchMarker(ShellTest):
    def test_build_wlan_refuses_a_tree_of_another_patch_set(self):
        s = (TOP / 'kernel' / 'build-wlan.sh').read_text()
        self.assertIn('[ "$(cat .mu300-patches)" = "$sum" ] ||', s)
        # the marker is the same sum build-all.sh's patched_copy writes
        self.assertIn('sum=$(cat /work/patches/wlan_combo-*.patch | sha256sum | cut -d" " -f1)', s)
        self.assertLess(s.index('if [ -f .mu300-patches ]'), s.index('make O=/src/out-linux'))

    def test_patched_copy_removes_only_its_own_copies(self):
        s = (TOP / 'kernel' / 'build-all.sh').read_text()
        body = s[s.index('patched_copy() {'):s.index('\n}\n', s.index('patched_copy() {'))]
        self.assertLess(body.index('case $1 in /src/ext-wlan_combo|/src/ext-sprdbt) ;;'), body.index('rm -rf "$1"'))
