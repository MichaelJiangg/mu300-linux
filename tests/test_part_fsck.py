"""No-console F2FS checks must answer one orphan-export prompt and then EOF."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('busybox'),'requires Linux BusyBox')
class PartitionFsck(unittest.TestCase):
    def test_prompt_is_bounded_and_worker_marker_is_always_removed(self):
        source=(ROOT/'desktop/boot/install-part.sh').read_text()
        source=source[:source.index('install_part_pending() {')]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'run').mkdir();(root/'repair/lib').mkdir(parents=True)
            loader=root/'repair/lib/ld-musl-aarch64.so.1'
            loader.write_text('#!/bin/sh\nread -r answer; [ "$answer" = n ] || exit 8\nif [ "$CASE" = extra ]; then read -r unexpected && exit 8; exit 255; fi\nexit "$CASE"\n');loader.chmod(0o755)
            source=source.replace('/run/',str(root)+'/run/').replace('/repair/',str(root)+'/repair/')
            for case in ('0','1','extra'):
                command=source+'\npart_fsck unused '+str(root)+'/check.log; rc=$?\n[ ! -e '+str(root)+'/run/part-check ] || exit 9\n[ ! -e '+str(root)+'/run/part-fsck.stdin ] || exit 9\nexit "$rc"\n'
                p=subprocess.run(['busybox','ash','-c',command],env=dict(os.environ,CASE=case),capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,255 if case=='extra' else int(case),p.stderr)
