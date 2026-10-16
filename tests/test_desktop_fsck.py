"""Internal-root repair happens before mounting and skips healthy filesystems."""
from helpers import ShellTest, TOP

class DesktopFsck(ShellTest):
    def test_clean_error_and_unknown_filesystems(self):
        source=(TOP/'desktop/boot/storage.sh').read_text()
        function=source[source.index('desktop_ext4_check() {'):source.index('\ndesktop_mount_root()')]
        loader=self.tmp/'loader'
        loader.write_text('#!/bin/sh\necho "$*" >> "$STUBLOG/fsck"\nexit "${TEST_FSCK_RC:-0}"\n')
        loader.chmod(0o755)
        function=function.replace('/repair/lib/ld-musl-aarch64.so.1',str(loader)).replace('/etc/mu300-desktop-fsck-force',str(self.tmp/'force'))
        function=function.replace('/run/mu300-root-fsck.log',str(self.tmp/'fsck.log'))
        self.stub('log','echo "$*" >> "$STUBLOG/log"')
        self.stub('setup_usb_gadget','echo usb-ready >> "$STUBLOG/usb"')
        root=self.tmp/'root';calls=self.tmp/'fsck'
        for shell in self.each_shell():
            for magic,state,rc,ok,called in [(0xef53,1,0,True,False),(0xef53,3,1,True,True),(0xef53,3,4,False,True),(0x1234,3,0,False,False)]:
                data=bytearray(4096);data[1080:1084]=magic.to_bytes(2,'little')+state.to_bytes(2,'little')
                root.write_bytes(data);calls.unlink(missing_ok=True);(self.tmp/'usb').unlink(missing_ok=True)
                r=self.sh(shell,function+'\ndesktop_ext4_check "$TEST_ROOT"',TEST_ROOT=root,TEST_FSCK_RC=str(rc))
                self.assertEqual(r.returncode==0,ok,r.stderr)
                self.assertEqual(calls.exists(),called)
                self.assertEqual((self.tmp/'usb').exists(),called)
                if called:self.assertIn('-fy '+str(root),calls.read_text())
        self.assertLess(source.index('desktop_ext4_check "$d"'),source.index('mount -t ext4 -o noatime "$d" /disk'))
