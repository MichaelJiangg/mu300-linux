"""TF capacity/metadata regressions: temporary files only, no device access."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
TOOLS = TOP/'tools'
BB = shutil.which('busybox')


class ManifestNewlines(unittest.TestCase):
    def test_requirements_are_ascii_lf_even_when_generated_on_windows(self):
        spec=importlib.util.spec_from_file_location('tf_requirements_manifest_fixture',TOOLS/'tf-payload-manifest.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('boot-linux.img','android-bootchain.sh','bootchain.sh'):(root/name).write_bytes(b'fixture')
            with tarfile.open(root/'mu300-openwrt.tar.gz','w:gz') as archive:
                for name in ('bin/busybox','sbin/procd','sbin/init','etc/uci-defaults/90-mu300','etc/init.d/mu300-vendor'):
                    entry=tarfile.TarInfo(name);entry.size=1;archive.addfile(entry,io.BytesIO(b'x'))
            module.manifest(root)
            data=(root/'rootfs.requirements').read_bytes()
            self.assertTrue(data.endswith(b'\n'))
            self.assertNotIn(b'\r',data)
            self.assertEqual(len(data.splitlines()),1)
            self.assertTrue(all(int(x)>0 for x in data.split()))
            sums=dict((name,digest) for digest,name in (line.split() for line in (root/'payload.sha256').read_text().splitlines()))
            self.assertEqual(sums['rootfs.requirements'],hashlib.sha256(data).hexdigest())


@unittest.skipUnless(os.name!='nt' and BB,'run the real BusyBox shell fixtures in Linux/WSL')
class RequirementsParsing(unittest.TestCase):
    def parse(self,data,sectors=61067008,old_read=False):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'rootfs.requirements';path.write_bytes(data)
            parser='read -r required_kib required_inodes < "$2"' if old_read else 'tf_read_requirements "$2"'
            script='. "$1"\n'+parser+' || exit 7\ntf_capacity "$3" "$required_kib" "$required_inodes" || exit 8\nprintf "%s %s\\n" "$required_kib" "$required_inodes"\n'
            env=dict(os.environ)
            # Exercise BusyBox awk too; do not replace any global command.
            wrapper=root/'awk';wrapper.write_text('#!/bin/sh\nexec "'+BB+'" awk "$@"\n');wrapper.chmod(0o755)
            env['PATH']=str(root)+os.pathsep+env['PATH']
            result=subprocess.run([BB,'sh','-c',script,'fixture',str(TOOLS/'tf-storage.sh'),str(path),str(sectors)],
                                  capture_output=True,text=True,env=env,timeout=5)
            self.assertEqual(path.read_bytes(),data)
            return result

    def test_reported_32g_card_accepts_lf_crlf_and_missing_final_newline(self):
        for data in (b'351656 18357\n',b'351656 18357\r\n',b'351656\t18357\r\n',b'351656 18357'):
            with self.subTest(data=data):
                result=self.parse(data)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,'351656 18357\n')

    def test_old_read_reproduces_crlf_false_rejection(self):
        self.assertEqual(self.parse(b'351656 18357\n',old_read=True).returncode,0)
        self.assertEqual(self.parse(b'351656 18357\r\n',old_read=True).returncode,8)

    def test_corrupt_metadata_and_true_capacity_shortage_are_distinct(self):
        for data in (b'',b'351656\n',b'351656 18357 extra\n',b'351656 18\r357\n',
                     b'0 18357\n',b'351656 0\n',b'-1 18357\n',b'35x 18357\n',b'351656 18357\n1 2\n'):
            with self.subTest(data=data):self.assertEqual(self.parse(data).returncode,7)
        self.assertEqual(self.parse(b'351656 18357\r\n',sectors=1024).returncode,8)

    def test_128g_and_256g_cards_have_no_artificial_size_cap(self):
        for size in (128,256):
            with self.subTest(gib=size):
                self.assertEqual(self.parse(b'351656 18357\r\n',sectors=(size<<30)//512).returncode,0)


@unittest.skipUnless(os.name!='nt' and BB,'run the file-only TF worker preflight in Linux/WSL')
class WorkerPreflight(unittest.TestCase):
    def test_actual_preflight_accepts_crlf_and_reports_capacity_vs_bad_metadata(self):
        for data,sectors,good,error in ((b'351656 18357\n',61067008,True,''),
                                        (b'351656 18357\r\n',61067008,True,''),
                                        (b'351656 invalid\r\n',61067008,False,'invalid rootfs.requirements'),
                                        (b'351656 18357\r\n',1024,False,'target=512 KiB, required=351656 KiB')):
            with self.subTest(data=data,sectors=sectors),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);bins=root/'bin';bins.mkdir()
                card=root/'card';card.touch();bootdev=root/'bootdev';bootdev.touch();misc=root/'misc';misc.touch()
                (root/'rootfs.requirements').write_bytes(data)
                for name in ('boot-linux.img','mu300-openwrt.tar.gz','rootfs-critical.sha256','android-bootchain.sh','bootchain.sh'):
                    (root/name).write_bytes(b'fixture')
                names=('rootfs.requirements','boot-linux.img','mu300-openwrt.tar.gz','rootfs-critical.sha256','android-bootchain.sh','bootchain.sh')
                (root/'payload.sha256').write_text(''.join(hashlib.sha256((root/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names))
                (root/'boot-linux.sha256').write_text(hashlib.sha256(b'fixture').hexdigest()+'\n')
                (root/'mu300-install.env').write_text('SD_MODE=1\nSD_DEV='+str(card)+'\nSYNC_BOOTCHAIN=0\n')
                shutil.copyfile(TOOLS/'tf-storage.sh',root/'tf-storage.sh')
                def stub(name,body):
                    path=bins/name;path.write_text('#!/bin/sh\n'+body+'\n');path.chmod(0o755);return path
                stub('awk','exec "'+BB+'" awk "$@"')
                stub('blockdev','case "$2" in "$CARD") echo "$CARD_SECTORS";; "$BOOT") echo 131072;; *) echo 8;; esac')
                stub('df','printf "Filesystem 1K-blocks Used Available Use%% Mounted\\nfixture 9999999 1 9999998 1%% /\\n"')
                mkfs=stub('mke2fs','[ "$1" = -V ] || { echo UNEXPECTED_FORMAT >&2; exit 99; }; echo "mke2fs fixture version"')
                source=(TOOLS/'tf-install-worker.sh').read_text()
                # BusyBox standalone ash can bypass PATH for its applets.
                # Shell functions intercept I/O even in that build mode.
                fake_io='''blockdev() { case "$2" in "$CARD") echo "$CARD_SECTORS";; "$BOOT") echo 131072;; *) echo 8;; esac; }
df() { printf 'Filesystem 1K-blocks Used Available Use%% Mounted\\nfixture 9999999 1 9999998 1%% /\\n'; }
'''
                source=source.replace('case ${1:-} in',fake_io+'case ${1:-} in',1)
                source=source.replace('/system/bin/mke2fs',str(mkfs)).replace('[ -b "$SD_DEV" ]','[ -f "$SD_DEV" ]')
                source=source.replace('[ -b "$MU300_TF_BOOTDEV" ]','[ -f "$MU300_TF_BOOTDEV" ]').replace('[ -b /dev/block/by-name/misc ]','[ -f "$MISC" ]')
                worker=root/'worker.sh';worker.write_text(source)
                env=dict(os.environ,MU300_PAYLOAD_DIR=temp,MU300_INSTALL_TMP=temp,MU300_BUSYBOX=BB,
                         MU300_TF_BIN=str(bins),MU300_TF_BOOTDEV=str(bootdev),CARD=str(card),BOOT=str(bootdev),MISC=str(misc),CARD_SECTORS=str(sectors))
                result=subprocess.run([BB,'sh',str(worker),'--preflight'],env=env,capture_output=True,text=True,timeout=10)
                output=result.stdout+result.stderr
                self.assertEqual(result.returncode==0,good,output)
                self.assertNotIn('UNEXPECTED_FORMAT',output)
                if error:self.assertIn(error,output)
                if good:self.assertIn('target=61067008 sectors; required=351656 KiB, 18357 inodes',output)
                self.assertEqual(card.stat().st_size,0)
                self.assertEqual(bootdev.stat().st_size,0)
                self.assertEqual(misc.stat().st_size,0)
                self.assertEqual((root/'rootfs.requirements').read_bytes(),data)


if __name__=='__main__':unittest.main()
