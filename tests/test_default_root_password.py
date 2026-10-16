"""Exercise the actual image-build password policy without touching host accounts."""
import unittest
try:
    import crypt
except ImportError:
    crypt = None
from helpers import TOP, ShellTest

@unittest.skipUnless(crypt, 'requires a platform crypt implementation')
class DefaultRootPassword(ShellTest):
    def test_fresh_image_root_password_and_other_accounts(self):
        text=(TOP/'openwrt/build-rootfs.sh').read_text()
        block=text.split('# --- default-root-password begin ---',1)[1].split('# --- default-root-password end ---',1)[0]
        root=self.tmp/'root';(root/'etc').mkdir(parents=True)
        path=root/'etc/shadow'
        for shell in self.each_shell():
            path.write_text('root::0:0:99999:7:::\ndaemon:!:0:0:99999:7:::\n')
            path.chmod(0o600)
            result=self.sh(shell,block,R=root)
            self.assertEqual(result.returncode,0,result.stderr)
            lines=path.read_text().splitlines()
            fields=lines[0].split(':')
            self.assertEqual(crypt.crypt('root',fields[1]),fields[1])
            self.assertNotEqual(crypt.crypt('wrong-password',fields[1]),fields[1])
            self.assertEqual(fields[2:],['0','0','99999','7','','',''])
            self.assertEqual(lines[1],'daemon:!:0:0:99999:7:::')
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            path.write_text('daemon:!:0:0:99999:7:::\n')
            result=self.sh(shell,block,R=root)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(path.read_text(),'daemon:!:0:0:99999:7:::\n')
