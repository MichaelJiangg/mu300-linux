"""A default image must not inherit optional VPN engines or stale menu entries."""
import hashlib
import io
from pathlib import Path
import runpy
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
policy=runpy.run_path(str(ROOT/'openwrt/no-vpn-payload.py'))

class NoVpn(unittest.TestCase):
    def archive(self,path,entries):
        with tarfile.open(path,'w:gz') as t:
            for name,content in entries.items():
                m=tarfile.TarInfo(name);m.size=len(content);m.mode=0o755
                t.addfile(m,io.BytesIO(content))

    def test_removes_engines_services_and_menu_but_preserves_network_modules(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rootfs.tar.gz'
            entries={f'opt/mu300/bin/{name}':b'engine' for name in ('xray','sing-box','hev-socks5-tunnel')}
            entries.update({'etc/init.d/mu300-vpn':b'start', 'etc/rc.d/S77mu300-vpn':b'start',
                'etc/mu300/vpn.conf.example':b'config',
                'opt/mu300/bin/mu300-toolkit':(ROOT/'rootfs/overlay/opt/mu300/bin/mu300-toolkit').read_bytes(),
                'lib/modules/7.2.8/tun.ko':b'kernel-module','opt/mu300/bin/mobile-data':b'cellular'})
            self.archive(p,entries);policy['strip'](p)
            with tarfile.open(p) as t:
                names=t.getnames();self.assertFalse(any(policy['forbidden'](n) for n in names))
                self.assertEqual(t.extractfile('lib/modules/7.2.8/tun.ko').read(),b'kernel-module')
                script=t.extractfile('opt/mu300/bin/mu300-toolkit').read().decode()
                self.assertNotIn('menu_vpn',script);self.assertNotIn('VPN_CONF',script)
                self.assertIn('8) menu_ttl ;;',script)
                self.assertEqual(subprocess.run(['sh','-n'],input=script,text=True,capture_output=True).returncode,0)
            policy['strip'](p)

    def test_inherited_vpn_package_fails_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rootfs.tar.gz';self.archive(p,{'lib/apk/packages/openvpn-2.6.list':b'installed'})
            before=hashlib.sha256(p.read_bytes()).digest()
            with self.assertRaisesRegex(ValueError,'VPN APK installed'):policy['strip'](p)
            self.assertEqual(hashlib.sha256(p.read_bytes()).digest(),before)

    def test_optional_build_inputs_are_not_mounted_or_copied(self):
        text=(ROOT/'openwrt/build-rootfs.sh').read_text()
        for name in ('xray','sing-box','hev-socks5-tunnel'):
            self.assertNotIn('$(opt '+name+' ',text)
            self.assertNotIn('cp /in/'+name,text)
        self.assertIn('python3 "$TOP/openwrt/no-vpn-payload.py"',text)
