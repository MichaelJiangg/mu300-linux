"""The fstools guard must run before probing/opening candidate devices."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from helpers import TOP

class BlockProbe(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc'), 'Linux C compiler required')
    def test_device_type_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=str(Path(tmp)/'guard')
            subprocess.run(['cc','-Wall','-Wextra','-Werror',str(TOP/'tests/block_probe_guard.c'),'-o',out],check=True)
            subprocess.run([out],check=True)

    def test_guard_is_before_probe(self):
        patch=(TOP/'openwrt/patches/fstools-probe-device-types.patch').read_text()
        self.assertIn('+\tif (!mu300_probe_allowed(path))',patch)
        guard=(TOP/'openwrt/block-probe-guard.h').read_text()
        self.assertNotIn('open(',guard)
        self.assertIn('/sys/dev/char/%u:%u/subsystem',guard)

    def test_rootfs_requires_patched_package(self):
        source=(TOP/'openwrt/build-rootfs.sh').read_text()
        self.assertIn('sh "$TOP/openwrt/build-block-mount.sh"',source)
        self.assertIn('apk add --allow-untrusted /in/block-mount-mu300.apk',source)
        for name in ('build-openwrt-tf-magisk.sh','make-release.sh'):
            source=(TOP/'tools'/name).read_text()
            self.assertIn('./etc/mu300/block-mount.build-id ',source)
            self.assertIn('./sbin/block ',source)
