"""Call audio and the kernels: call audio is the audio extra's (github.com/dikeckaan/mu300-audio). What stays here is
the memory reserved at boot and the sound core options its drivers build against."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

UP = TOP / 'upstream'
OVERLAY = TOP / 'rootfs' / 'overlay'


class StaysInTheKernel(unittest.TestCase):
    def test_kernel_config(self):
        cfg = (UP / 'mu300-mainline.config').read_text()
        for opt in ('CONFIG_SND_SOC=m', 'CONFIG_SND_SOC_SPRD=m', 'CONFIG_SND_DYNAMIC_MINORS=y', 'CONFIG_DMADEVICES=y',
                    'CONFIG_OF_RESERVED_MEM_ADD="0xaf600000,3M;0xaf900000,7M"'):
            self.assertIn(opt + '\n', cfg)
        # the 5.4 kernel reserves the same ranges
        self.assertIn('CONFIG_OF_RESERVED_MEM_ADD="0xaf600000,3M;0xaf900000,7M"',
                      (TOP / 'kernel' / 'mu300-linux.fragment').read_text())
        exclude = (UP / 'all-modules.exclude').read_text()
        self.assertRegex(exclude, r'(?m)^dir sound/soc$')

    def test_reservation_patch(self):
        patch = (UP / 'patches' / '0022-of-reserved-mem-add.patch').read_text()
        self.assertIn('+config OF_RESERVED_MEM_ADD', patch)
        self.assertIn('+	reserved_mem_add_regions();', patch)
        # pages kept (memblock_reserve, not no-map)
        self.assertIn('memblock_reserve(base, size)', patch)
        self.assertTrue((TOP / 'kernel' / 'patches' / 'of-reserved-mem-add.patch').is_file())

    def test_the_kernel_checks_every_control_write(self):
        self.assertIn('CONFIG_SND_CTL_INPUT_VALIDATION=y\n', (UP / 'mu300-mainline.config').read_text())

    def test_the_guard_never_blocks_what_the_stack_needs(self):
        blocked = {l.split('#')[0].strip() for l in
                   (OVERLAY / 'opt' / 'mu300' / 'lib' / 'autoload-blocked').read_text().splitlines()}
        for m in ('snd_soc_core', 'snd_compress', 'snd_pcm', 'snd_timer', 'snd'):
            self.assertNotIn(m, blocked)


class NotHereAnyMore(unittest.TestCase):
    def test_no_driver_of_the_stack_is_built(self):
        self.assertFalse((UP / 'modules' / 'sprd_audio').exists())
        self.assertFalse((TOP / 'kernel' / 'build-audio.sh').exists())
        src = (UP / 'build-modules.sh').read_text()
        mods = re.search(r'mods=\$\{\*:-([^}]*)\}', src).group(1).split()
        self.assertNotIn('sprd_audio', mods)
        self.assertNotIn('virt-dma', src)
        for p in ('audio-*.patch', 'mcdt-enable-clock.patch', 'sprd-card-dummy-on-defer.patch'):
            self.assertEqual(list((TOP / 'kernel' / 'patches').glob(p)), [], p)

    def test_no_program_or_service_of_the_stack_is_in_the_images(self):
        for f in ('opt/mu300/bin/mu300-audio-dsp', 'opt/mu300/bin/mu300-voice', 'etc/systemd/system/mu300-audio.service',
                  'etc/systemd/system/mu300-voice.service', 'etc/modprobe.d/mu300-audio.conf'):
            self.assertFalse((OVERLAY / f).exists(), f)
        for f in ('etc/init.d/mu300-audio', 'etc/init.d/mu300-voice'):
            self.assertFalse((TOP / 'openwrt' / 'overlay' / f).exists(), f)
        for t in ('pcmhost', 'ctlset', 'hfp'):
            self.assertFalse((TOP / 'tools' / t).exists(), t)
        self.assertNotIn('mu300-voice', (OVERLAY / 'opt/mu300/lib/path-commands').read_text().split())
        self.assertNotIn('mu300-audio.service', (TOP / 'rootfs' / 'assemble.sh').read_text())
        self.assertNotIn('mu300-voice', (OVERLAY / 'etc/tmpfiles.d/mu300-run.conf').read_text().split('\n', 3)[-1])

    def test_ubuntu_leaves_the_card_state_alone(self):
        # the image masks alsa-utils' restore service and udev rule (harmless without the audio extra, needed with
        # it); run its lines.
        src = (TOP / 'rootfs' / 'assemble.sh').read_text()
        lines = [l for l in src.splitlines()
                 if ('alsa' in l or l == 'mkdir -p $R/etc/udev/rules.d') and not l.lstrip().startswith('#')]
        self.assertEqual(len(lines), 4)
        with tempfile.TemporaryDirectory() as d:
            r = Path(d) / 'root'
            subprocess.run(['sh', '-ec', 'mkdir -p $R/etc/systemd/system\n' + '\n'.join(lines)],
                           env={'R': str(r), 'PATH': '/usr/bin:/bin'}, check=True)
            for f in ('etc/systemd/system/alsa-restore.service', 'etc/systemd/system/alsa-state.service',
                      'etc/udev/rules.d/90-alsa-restore.rules'):
                self.assertTrue((r / f).is_symlink(), f)
                self.assertEqual(str((r / f).readlink()), '/dev/null', f)
        self.assertLess(src.index('90-alsa-restore.rules'), src.index('tar --numeric-owner'))


if __name__ == '__main__':
    unittest.main()
