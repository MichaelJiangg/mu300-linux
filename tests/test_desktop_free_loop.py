"""Opt-in real ext4/GPT fixture on a sparse file, never on a hardware disk.

Linux root: MU300_TEST_FREE_LOOP=1 python3 -m unittest discover -s tests -p test_desktop_free_loop.py
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_desktop_free_space import snapshot, m, TOP

@unittest.skipUnless(os.name=='posix' and getattr(os,'geteuid',lambda:1)()==0 and
                     os.environ.get('MU300_TEST_FREE_LOOP')=='1','opt-in Linux root loop fixture')
class RealLoop(unittest.TestCase):
    def command(self,*args):
        p=subprocess.run(args,capture_output=True,text=True,timeout=120)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        return p.stdout

    def fixture(self,wrong_file=False,changed_gpt=False):
        for tool in ('losetup','mkfs.ext4','debugfs','e2fsck','resize2fs','mount','bash'):
            if not shutil.which(tool):self.skipTest('missing fixture tool '+tool)
        with tempfile.TemporaryDirectory(prefix='mu300-free-range-') as tmp:
            base=Path(tmp);disk=base/'disk';stage=base/'stage';stage.mkdir()
            payload=base/'payload';payload.mkdir()
            total=6*2097152;first,last=snapshot(total,[('userdata',2048,2*2097152-1)])
            start=2*2097152;need=2*2097152
            newfirst,newlast=m.gpt_add_root(first,last,total,start,need)
            tail=total-len(last)//512
            before=b'BEFORE-ROOT-GUARD';after=b'AFTER-ROOT-GUARD!'
            with disk.open('wb') as f:f.truncate(total*512)
            with disk.open('r+b') as f:
                f.write(first);f.seek(tail*512);f.write(last)
                f.seek(start*512-len(before));f.write(before)
                f.seek((start+need)*512);f.write(after)
            for name,data in [('before-first',first),('before-last',last),('new-first',newfirst),('new-last',newlast)]:
                (payload/('gpt-'+name+'.bin')).write_bytes(data)
            image=stage/'openwrt.ext4.new'
            with image.open('wb') as f:f.truncate(32<<20)
            self.command('mkfs.ext4','-q','-F','-b','4096',str(image))
            marker=base/'marker';marker.write_text('verified root\n')
            self.command('debugfs','-w','-R',f'write {marker} /marker',str(image))
            checksum='0'*64 if wrong_file else hashlib.sha256(marker.read_bytes()).hexdigest()
            (stage/'image.sha256').write_text(checksum+'  marker\n');(stage/'image-root').mkdir()
            image_hash=hashlib.sha256(image.read_bytes()).hexdigest()
            repair=payload/'desktop/files/boot/repair';(repair/'lib').mkdir(parents=True)
            (repair/'usr/sbin').mkdir(parents=True)
            loader=repair/'lib/ld-musl-aarch64.so.1';loader.write_text('#!/bin/sh\nshift 2\nexec "$@"\n');loader.chmod(0o755)
            for tool in ('e2fsck','resize2fs'):(repair/'usr/sbin'/tool).symlink_to(shutil.which(tool))
            shutil.copyfile(TOP/'desktop/android-loop.sh',payload/'android-loop.sh')
            sysroot=base/'sys';(sysroot/'device').mkdir(parents=True)
            (sysroot/'device/cid').write_text('a'*32);(sysroot/'size').write_text(str(total))
            script=(TOP/'desktop/android-write-free.sh').read_text()
            # Substitute only Android's identity/app binding with fixture data.
            # Actual loop ioctls, raw dd, ext4 repair/growth, mount and GPT writes run.
            script=script.replace('/dev/block/mmcblk[0-9]',str(disk)).replace('/sys/class/block/$node',str(sysroot))
            script=script.replace('[ -b "$disk" ]','[ -f "$disk" ]')
            script=script.replace('/system/bin/losetup',shutil.which('losetup')).replace(' -S ',' --sizelimit ')
            script=script.replace("grep -q -- '-S'","grep -q -- '--sizelimit'")
            job=base/'run.sh';job.write_text(script)
            if changed_gpt:
                first=b'X'+first[1:]
                with disk.open('r+b') as f:f.write(first)
            env=dict(os.environ,MU300_PAYLOAD_DIR=str(payload),MU300_INSTALL_TMP=str(stage))
            try:
                result=subprocess.run(['bash',str(job),str(disk),'a'*32,str(total),str(start),str(need),
                    image_hash,str(len(first)//512),str(tail)],env=env,capture_output=True,text=True,timeout=120)
                if wrong_file or changed_gpt:self.assertNotEqual(result.returncode,0)
                else:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                with disk.open('rb') as f:
                    self.assertEqual(f.read(len(first)),first if wrong_file or changed_gpt else newfirst)
                    f.seek(tail*512);self.assertEqual(f.read(len(last)),last if wrong_file or changed_gpt else newlast)
                    f.seek(start*512-len(before));self.assertEqual(f.read(len(before)),before)
                    f.seek((start+need)*512);self.assertEqual(f.read(len(after)),after)
                    if changed_gpt:
                        f.seek(start*512);self.assertEqual(f.read(4096),bytes(4096))
            finally:
                self.assertFalse(self.command('losetup','-j',str(disk)).strip(),'fixture loop leaked')

    def test_real_ext4_grows_to_selected_size_and_adjacent_ranges_survive(self):self.fixture()
    def test_bad_root_file_never_commits_partition_table(self):self.fixture(wrong_file=True)
    def test_changed_gpt_aborts_before_touching_free_range(self):self.fixture(changed_gpt=True)

if __name__=='__main__':unittest.main()
