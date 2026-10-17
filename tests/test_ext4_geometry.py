"""Real offline ext4 growth on sparse files; never operates on hardware."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from helpers import TOP, shells

CHECKER=TOP/'desktop/boot/ext4-geometry.sh'


@unittest.skipUnless(os.name=='posix' and all(shutil.which(n) for n in ('mkfs.ext4','resize2fs','e2fsck','debugfs')), 'Linux ext4 tools required')
class Geometry(unittest.TestCase):
    def verify(self,shell,image,sectors):
        return subprocess.run(shell+['-c','. "$1"; ext4_verify_grown "$2" "$3"','verify',str(CHECKER),str(image),str(sectors)],capture_output=True,text=True)

    def test_exact_and_tiny_tail_growth_preserves_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'root.ext4';proof=root/'proof';proof.write_text('OpenWrt firmware proof')
            subprocess.run(['mkfs.ext4','-q','-F','-b','4096',str(image),'128M'],check=True,capture_output=True)
            subprocess.run(['debugfs','-w','-R',f'write {proof} /proof',str(image)],check=True,capture_output=True)
            for wanted,actual in [(65536,65536),(65787,65536),(81920,81920)]:
                with image.open('r+b') as f:f.truncate(wanted*4096)
                subprocess.run(['resize2fs',str(image)],check=True,capture_output=True)
                subprocess.run(['e2fsck','-fn',str(image)],check=True,capture_output=True)
                with image.open('rb') as f:f.seek(1028);self.assertEqual(int.from_bytes(f.read(4),'little'),actual)
                for shell in shells():
                    result=self.verify(shell,image,wanted*8)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(subprocess.check_output(['debugfs','-R','cat /proof',str(image)],stderr=subprocess.DEVNULL),proof.read_bytes())
            for sectors in [32768*8,10*32768*8]:
                for shell in shells():self.assertNotEqual(self.verify(shell,image,sectors).returncode,0)

    def test_initramfs_worker_reaches_valid_partial_group_and_rejects_noop(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'root.ext4';loader=root/'loader'
            loader.write_text('#!/bin/sh\nshift 2\nexec "$@"\n');loader.chmod(0o755)
            source=(TOP/'desktop/boot/part-progress.sh').read_text().replace('/etc/ext4-geometry.sh',str(CHECKER))
            source=source.replace('/repair/lib/ld-musl-aarch64.so.1',str(loader)).replace('/repair/usr/sbin/resize2fs',shutil.which('resize2fs')).replace('/repair/usr/sbin/e2fsck',shutil.which('e2fsck')).replace('/run/part-growfs.log',str(root/'grow.log'))
            for shell in shells():
                image.unlink(missing_ok=True)
                subprocess.run(['mkfs.ext4','-q','-F','-b','4096',str(image),'128M'],check=True,capture_output=True)
                with image.open('r+b') as f:f.truncate(65792*4096)
                result=subprocess.run(shell+['-c',source+'\npart_grow_ext4 "$1" 526336','fixture',str(image)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr+(root/'grow.log').read_text())
                noop=root/'noop';noop.write_text('#!/bin/sh\nexit 0\n');noop.chmod(0o755)
                result=subprocess.run(shell+['-c',source.replace(shutil.which('resize2fs'),str(noop))+'\npart_grow_ext4 "$1" 2621440','fixture',str(image)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)

    def test_missing_helper_stops_desktop_workers_before_any_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'desktop-settings.env').touch()
            for name in ('android-write-part.sh','android-write-free.sh'):
                result=subprocess.run(['busybox','ash',str(TOP/'desktop'/name)],env=dict(os.environ,MU300_PAYLOAD_DIR=str(root),MU300_INSTALL_TMP=str(root)),capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('ext4-geometry.sh',result.stderr)
                self.assertFalse((root/'openwrt.ext4.new').exists())


if __name__=='__main__':unittest.main()
