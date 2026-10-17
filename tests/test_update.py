"""mu300-update, sourced for its functions (MU300_LIB=1) against a fake Linux partition (MU300_DISK): which files of a
release it takes, the kernel choice, the byte helpers it edits boot image headers with, and whether a kernel bundle
may go onto this device."""
import io
import os
import shutil
import struct
import tarfile
import unittest

from helpers import BIN, TOP, ShellTest


class Update(ShellTest):
    def setUp(self):
        super().setUp()
        self.disk = self.tmp / 'disk'
        (self.disk / 'ubuntu' / 'etc').mkdir(parents=True)
        self.root = self.tmp / 'root'
        (self.root / 'run/mu300').mkdir(parents=True)
        self.device('f50')

    def device(self, name):
        (self.root / 'run/mu300/device').write_text(name + '\n')

    def up(self, shell, code, **env):
        return self.sh(shell, f'. "{BIN}/mu300-update"; {code}', MU300_LIB=1, MU300_DISK=self.disk, MU300_BIN=BIN,
                       MU300_SYSROOT=self.root, **env)

    def test_sourcing_does_nothing(self):
        for shell in self.each_shell():
            r = self.up(shell, 'echo loaded')
            self.assertEqual((r.returncode, r.stdout), (0, 'loaded\n'), r.stderr)

    @unittest.skipUnless(shutil.which('busybox'), 'requires the real BusyBox cp applet')
    def test_busybox_existing_directory_regression(self):
        source, target = self.tmp / 'source', self.tmp / 'target'
        source.mkdir(); target.mkdir()
        (source / 'wcnmodem.bin').write_bytes(b'firmware')
        (target / 'regulatory.db').write_bytes(b'image')
        for shell in self.each_shell():
            # Reproduce the old implementation, then test the replacement
            # against the same applet (not GNU cp behind a mocked shell).
            (target / 'wcnmodem.bin').unlink(missing_ok=True)
            r = self.up(shell, f'busybox cp -an "{source}/." "{target}/"')
            # Older BusyBox builds reject -n outright; the old updater hid
            # that error with `|| true`, causing the same missing firmware.
            if r.returncode:
                self.assertIn('invalid option', r.stderr)
            self.assertFalse((target / 'wcnmodem.bin').exists())
            r = self.up(shell, f'cp() {{ busybox cp "$@"; }}; copy_missing "{source}" "{target}"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((target / 'wcnmodem.bin').read_bytes(), b'firmware')
            self.assertEqual((target / 'regulatory.db').read_bytes(), b'image')

    def test_copy_missing_preserves_image_entries_and_links(self):
        source, target, outside = self.tmp / 'source', self.tmp / 'target', self.tmp / 'outside'
        (source / 'blocked/subdir').mkdir(parents=True)
        (source / 'blocked/subdir/no-write').write_text('vendor')
        (source / 'dangling').mkdir()
        (source / 'dangling/no-write').write_text('vendor')
        (source / 'name with space').write_text('vendor')
        (source / '.hidden').write_text('hidden')
        (source / 'kept').write_text('old')
        (source / 'link').symlink_to('name with space')
        target.mkdir(); outside.mkdir()
        (target / 'blocked').symlink_to(outside)
        (target / 'dangling').symlink_to(outside / 'absent')
        (target / 'kept').write_text('image')
        for shell in self.each_shell():
            r = self.up(shell, f'copy_missing "{source}" "{target}"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual((target / 'kept').read_text(), 'image')
            self.assertEqual((target / 'name with space').read_text(), 'vendor')
            self.assertEqual((target / '.hidden').read_text(), 'hidden')
            self.assertEqual(os.readlink(target / 'link'), 'name with space')
            for name in ('name with space', '.hidden', 'link'):
                (target / name).unlink()
            r = self.up(shell, f'copy_missing "{source}" "{target}/blocked"')
            self.assertNotEqual(r.returncode, 0)

    def vendor_update_fixture(self):
        old = self.disk / 'openwrt'
        files = {'opt/mu300/android/system/bin/cltest': b'old',
                 'opt/mu300/android/vendor/bin/modem_control': b'vendor',
                 'opt/mu300/android/dev-properties/property_info': b'properties',
                 'lib/firmware/wcnmodem.bin': b'firmware',
                 'lib/firmware/wifi_board_config.ini': b'board',
                 'lib/firmware/regulatory.db': b'old',
                 'lib/modules/7.2.8/wcn_bsp.ko': b'module',
                 'etc/unisoc-modem/cpu-voltage.json': b'{"offsets":[0,0,0]}',
                 'etc/config/wireless': b'my-settings',
                 'etc/crontabs/root': b'*/5 * * * * /root/check-link\n'}
        for name, data in files.items():
            path = old / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        stage = self.disk / '.mu300-update'
        stage.mkdir(exist_ok=True)
        with tarfile.open(stage / 'mu300-openwrt-rootfs.tar.gz', 'w:gz') as archive:
            for name, data in [('sbin/init', b'#!/bin/sh\n'),
                               ('etc/mu300/image-version', b'test-new\n'),
                               ('lib/firmware/regulatory.db', b'image'),
                               ('opt/mu300/android/system/bin/cltest', b'image')]:
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o755 if name == 'sbin/init' else 0o644
                archive.addfile(member, io.BytesIO(data))
        return old, files

    def test_update_carries_vendor_files_before_switch(self):
        for shell in self.each_shell():
            old, files = self.vendor_update_fixture()
            r = self.up(shell, 'sync() { :; }; is_root() { false; }; apply_one openwrt test-new')
            self.assertEqual(r.returncode, 0, r.stderr)
            for name, data in files.items():
                expected = b'image' if name.endswith(('cltest', 'regulatory.db')) else data
                self.assertEqual((old / name).read_bytes(), expected, name)
                self.assertEqual((self.disk / 'openwrt.old' / name).read_bytes(), data)
            self.assertEqual((old / 'etc/mu300/image-version').read_text(), 'test-new\n')
            shutil.rmtree(old)
            shutil.rmtree(self.disk / 'openwrt.old')

    def test_vendor_copy_failure_keeps_old_system(self):
        for shell in self.each_shell():
            old, files = self.vendor_update_fixture()
            r = self.up(shell, '''sync() { :; }; is_root() { false; };
                cp() { case "$*" in *wcnmodem.bin*) return 1;; esac; command cp "$@"; }
                apply_one openwrt test-new''')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('copying the vendor files failed', r.stderr)
            self.assertFalse((self.disk / 'openwrt.old').exists())
            self.assertFalse((self.disk / 'openwrt.new').exists())
            for name, data in files.items():
                self.assertEqual((old / name).read_bytes(), data)
            shutil.rmtree(old)

    def test_rootfs_asset(self):
        osr = self.disk / 'ubuntu' / 'etc' / 'os-release'
        cases = [('24.04', {}, 'mu300-ubuntu-rootfs.tar.gz'),
                 ('26.04', {}, 'mu300-ubuntu-26.04-rootfs.tar.gz'),
                 ('26.04', {'MU300_UBUNTU': '24.04'}, 'mu300-ubuntu-rootfs.tar.gz'),
                 ('24.04', {'MU300_UBUNTU': '26.04'}, 'mu300-ubuntu-26.04-rootfs.tar.gz'),
                 (None, {}, 'mu300-ubuntu-rootfs.tar.gz')]
        for shell in self.each_shell():
            for ver, env, want in cases:
                if ver:
                    osr.write_text(f'NAME="Ubuntu"\nVERSION_ID="{ver}"\n')
                else:
                    osr.unlink(missing_ok=True)
                self.assertEqual(self.up(shell, 'rootfs_asset ubuntu', **env).stdout.strip(), want, (ver, env))
            self.assertEqual(self.up(shell, 'rootfs_asset openwrt').stdout.strip(), 'mu300-openwrt-rootfs.tar.gz')

    def test_kernel_choice(self):
        boot = self.disk / 'boot'
        boot.mkdir()
        cases = [(None, '5.4', 'mu300-kernel.tar.gz'), ('6.18', '6.18', 'mu300-kernel-6.18.tar.gz'),
                 ('7.2', '7.2', 'mu300-kernel-7.2.tar.gz'), ('5.4', '5.4', 'mu300-kernel.tar.gz'),
                 ('6.1', '5.4', 'mu300-kernel.tar.gz'), ('', '5.4', 'mu300-kernel.tar.gz')]
        for shell in self.each_shell():
            for c, choice, asset in cases:
                f = boot / 'kernel'
                if c is None:
                    f.unlink(missing_ok=True)
                else:
                    f.write_text(c + '\n')
                self.assertEqual(self.up(shell, 'kernel_choice; kernel_asset').stdout.split(), [choice, asset], c)

    def test_byte_helpers(self):
        # the boot image header is edited with these: sizes little endian, the AVB footer big endian
        f = self.tmp / 'bytes.bin'
        for shell in self.each_shell():
            for v in (0, 1, 255, 256, 0x12345678, 0xFFFFFFFF):
                r = self.up(shell, f'bytes {v} 4 le > "{f}"; u32 "{f}" 0')
                self.assertEqual(f.read_bytes(), struct.pack('<I', v), v)
                self.assertEqual(r.stdout.strip(), str(v))
            for v in (0, 0x1234, 0x0000000100000000, 0x7FFFFFFF12345678):
                r = self.up(shell, f'bytes {v} 8 be > "{f}"; be64 "{f}" 0')
                self.assertEqual(f.read_bytes(), struct.pack('>Q', v), v)
                self.assertEqual(r.stdout.strip(), str(v))
            # poke: overwrite in place, the rest untouched
            f.write_bytes(bytes(16))
            self.up(shell, f'bytes 3735928559 4 le | poke "{f}" 4')
            self.assertEqual(f.read_bytes(), bytes(4) + struct.pack('<I', 0xDEADBEEF) + bytes(8))

    def test_pad_page(self):
        f = self.tmp / 'img'
        for shell in self.each_shell():
            for n, want in ((0, 0), (1, 4096), (4095, 4096), (4096, 4096), (4097, 8192)):
                f.write_bytes(b'x' * n)
                self.up(shell, f'pad_page "{f}"')
                self.assertEqual(f.stat().st_size, want, n)

    def test_installed_systems(self):
        for shell in self.each_shell():
            self.assertEqual(self.up(shell, 'installed_systems').stdout.split(), ['ubuntu'])
            (self.disk / 'openwrt').mkdir(exist_ok=True)
            self.assertEqual(self.up(shell, 'installed_systems').stdout.split(), ['ubuntu', 'openwrt'])
            (self.disk / 'openwrt').rmdir()

    def bundle(self, name, devices):
        p = self.tmp / name
        with tarfile.open(p, 'w:gz') as t:
            for fn, data in [('./Image', b'kernel'), ('./ramdisk-generic.lz4', b'rd')] + (
                    [('./devices', devices.encode())] if devices is not None else []):
                ti = tarfile.TarInfo(fn)
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
        return p

    def test_bundle_runs_here(self):
        new = self.bundle('new.tar.gz', 'f50 u30air\n')
        old = self.bundle('old.tar.gz', None)
        f50only = self.bundle('f50.tar.gz', 'f50\n')
        v50 = self.bundle('v50.tar.gz', 'f50 v50 u30air\n')
        cases = [('f50', new, True), ('f50', old, True), ('u30air', new, True), ('u30air', old, False),
                 ('u30air', f50only, False), ('v50', v50, True), ('v50', old, False),
                 ('v50', new, False), ('v50', f50only, False), ('f50', v50, True)]
        for shell in self.each_shell():
            for dev, b, ok in cases:
                self.device(dev)
                d = self.tmp / 'x'
                d.mkdir(exist_ok=True)
                r = self.up(shell, f'tar -tzf "{b}" > "{d}/list"; bundle_runs_here "{b}" "{d}/list" "{d}" && echo YES || echo NO')
                self.assertEqual(r.stdout.strip(), 'YES' if ok else 'NO', (dev, b.name, r.stderr))
                (d / 'devices').unlink(missing_ok=True)

    def test_v50_is_advertised_only_for_an_aw9523b_kernel(self):
        source=(TOP/'upstream/make-bundle.sh').read_text()
        start=source.index("devices='f50 u30air'")
        end=source.index('\ntar -C "$W/b"',start)
        code=source[start:end]
        build=self.tmp/'build';build.mkdir()
        stage=self.tmp/'stage';(stage/'b').mkdir(parents=True)
        for shell in self.each_shell():
            for config,expected in [('CONFIG_LEDS_AW9523B=y\n',True),
                                    ('CONFIG_LEDS_AW9523B=m\n',False),
                                    ('# CONFIG_LEDS_AW9523B is not set\n',False)]:
                (build/'kernel.config').write_text(config)
                result=self.sh(shell,code,UO=build,W=stage)
                self.assertEqual(result.returncode,0,result.stderr)
                boards=(stage/'b/devices').read_text().split()
                self.assertEqual('v50' in boards,expected)
                self.assertIn('f50',boards)
                self.assertIn('u30air',boards)
                self.assertEqual((stage/'b/features').read_text().splitlines(),['sdcard','linux-slot','gpt-root'])


if __name__ == '__main__':
    unittest.main()
