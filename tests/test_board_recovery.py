"""Generated board metadata recovery with OpenWrt's real ucode parser.

MU300_WRT_IMAGE=mu300-openwrt-base:25.12.5 python -m unittest discover -s tests -p test_board_recovery.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'rootfs/overlay/opt/mu300/bin/openwrt-board-check'
IMAGE=os.environ.get('MU300_WRT_IMAGE')

@unittest.skipUnless(IMAGE and shutil.which('docker'),'OpenWrt Docker fixture is opt-in')
class BoardRecovery(unittest.TestCase):
    def run_case(self,original,generated):
        with tempfile.TemporaryDirectory(prefix='mu300-board-') as tmp:
            root=Path(tmp);cfg=root/'root/etc/board.json';cfg.parent.mkdir(parents=True)
            cfg.write_bytes(original)
            wireless=cfg.parent/'config/wireless';wireless.parent.mkdir();wireless.write_bytes(b'USER SETTINGS\n')
            (root/'generated').write_bytes(generated)
            detector=root/'detector'
            detector.write_text('#!/bin/sh\necho invoked >> /fixture/detector-called\ncp /fixture/generated "$1"\n',newline='\n')
            # chmod inside the fixture also works on Windows bind mounts.
            result=subprocess.run(['docker','run','--rm','--platform','linux/arm64',
                '-v',str(SCRIPT)+':/check:ro','-v',str(root)+':/fixture',
                '-e','MU300_SYSROOT=/fixture/root','-e','MU300_BOARD_DETECTOR=/fixture/detector',
                IMAGE,'sh','-c','chmod +x /fixture/detector; sh /check'],capture_output=True,text=True,timeout=30)
            self.assertEqual(wireless.read_bytes(),b'USER SETTINGS\n')
            self.assertFalse(list(cfg.parent.glob('board.json.rebuild.*')))
            return result,cfg.read_bytes(),[p.read_bytes() for p in cfg.parent.glob('board.json.corrupt.*')],(root/'detector-called').exists()

    def test_valid_custom_metadata_is_preserved_without_regeneration(self):
        original=b'{"model":{"name":"custom"},"wlan":{"phy0":{"custom":true}}}\n'
        r,data,backups,called=self.run_case(original,b'{}')
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(data,original)
        self.assertEqual(backups,[]);self.assertFalse(called)

    def test_corrupt_metadata_is_backed_up_and_atomically_replaced(self):
        original=b'bad\0JSON\xff';generated=b'{"model":{"name":"V50"}}\n'
        r,data,backups,called=self.run_case(original,generated)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(data,generated)
        self.assertEqual(backups,[original]);self.assertTrue(called)

    def test_failed_regeneration_leaves_original_and_wireless_untouched(self):
        r,data,backups,called=self.run_case(b'broken',b'[1,2]')
        self.assertNotEqual(r.returncode,0);self.assertEqual(data,b'broken')
        self.assertEqual(backups,[]);self.assertTrue(called)

if __name__=='__main__':unittest.main()
