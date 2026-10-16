"""Offline fault injection: regular files/mocks only, never a physical disk."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import unittest

from helpers import TOP

TOOLS = TOP / 'tools'
BB = shutil.which('busybox')


def run_shell(code, *args, env=None, timeout=15):
    return subprocess.run(['sh', '-c', code, 'test', *map(str, args)],
                          env=env, capture_output=True, text=True, timeout=timeout)


class StoragePrimitives(unittest.TestCase):
    def test_only_exited_tasks_without_namespace_may_be_skipped(self):
        for state, namespace, gone in [('Z', False, True), ('X', False, True),
                                       ('S', False, False), ('R', False, False), ('Z', True, False)]:
            with self.subTest(state=state, namespace=namespace), tempfile.TemporaryDirectory() as tmp:
                proc = Path(tmp)
                (proc / 'mountinfo').touch()
                (proc / 'status').write_text(f'State:\t{state} (test)\n')
                (proc / 'ns').mkdir()
                if namespace: (proc / 'ns/mnt').symlink_to('mnt:[123]')
                r = run_shell('. "$1"; tf_namespace_gone "$2"', TOOLS / 'tf-storage.sh', proc)
                self.assertEqual(r.returncode == 0, gone, r.stdout + r.stderr)

    def test_alias_mounts_matched_by_devnum_not_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            mounts = Path(tmp) / 'mountinfo'
            mounts.write_text('31 1 179:33 / /mnt/media_rw/CARD rw - ext4 /dev/block/vold/public:179,33 rw\n'
                              '32 1 8:1 / /mnt/OTHER rw - vfat /dev/block/sda1 rw\n'
                              '33 1 179:33 /sub /storage/CARD rw - ext4 /dev/alias rw\n')
            r = run_shell('. "$1"; tf_mounts_for_ids " 179:33" "$2"', TOOLS / 'tf-storage.sh', mounts)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines(), ['31 /mnt/media_rw/CARD', '33 /storage/CARD'])

    def test_aligned_read_rejects_short_or_failed_read(self):
        for sectors, length, fail, success in [(8, 4096, False, True), (7, 4096, False, False),
                                                (8, 4095, False, False), (8, 4096, True, False)]:
            with self.subTest(sectors=sectors, length=length, fail=fail), tempfile.TemporaryDirectory() as tmp:
                disk = Path(tmp) / 'disk'
                disk.write_bytes(b'x' * length)
                code = '''. "$1"
T=$2
blockdev() { echo "$SECTORS"; }
dd() { [ "$FAIL" = 0 ] || return 1; command dd "$@"; }
tf_read_super "$3"
'''
                r = run_shell(code, TOOLS / 'tf-storage.sh', tmp, disk,
                              env=dict(os.environ, SECTORS=str(sectors), FAIL=str(int(fail))))
                self.assertEqual(r.returncode == 0, success, r.stdout + r.stderr)
                if sectors < 8:
                    self.assertFalse((Path(tmp) / 'tf-super').exists())

    def test_capacity_including_128_gib_without_size_cap(self):
        for sectors, kib, good in [(268435456, 600000, True), (1024, 600000, False),
                                   (-1, 1, False), (0, 1, False)]:
            r = run_shell('. "$1"; tf_capacity "$2" "$3" 20000', TOOLS / 'tf-storage.sh', sectors, kib)
            self.assertEqual(r.returncode == 0, good)

    def test_release_targets_only_selected_volume_and_refuses_namespace_residue(self):
        original = (TOOLS / 'tf-storage.sh').read_text()
        cases = [('mounted', 'unmounted', True), ('mounted_ro', 'unmounted', True),
                 ('mounted', 'unmountable', True), ('unmounted', 'unmounted', True),
                 ('unmountable', 'unmountable', True), ('mounted', 'mounted', False),
                 ('checking', 'checking', False), ('ejecting', 'ejecting', False),
                 ('removed', 'removed', False), ('formatting', 'formatting', False),
                 ('unknown', 'unknown', False)]
        for before, after, safe, residue in [(b, a, s, r) for b, a, s in cases for r in (False, True)]:
            with self.subTest(before=before, after=after, residue=residue), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name, text in [('sys/mmcblk1/dev', '179:32'), ('sys/mmcblk1p1/dev', '179:33'),
                                   ('sys/mmcblk1p2/dev', '179:34'), ('proc/self/mountinfo', ''),
                                   ('proc/42/mountinfo', '30 1 179:33 / /stale rw - ext4 /dev/alias rw\n' if residue else '')]:
                    p = root / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(text)
                script = original.replace('/sys/class/block/', str(root / 'sys') + '/')
                script = script.replace('/proc/self/mountinfo', str(root / 'proc/self/mountinfo'))
                script = script.replace('/proc/[0-9]*/mountinfo', str(root / 'proc') + '/[0-9]*/mountinfo')
                path = root / 'storage.sh'; path.write_text(script)
                code = '''. "$1"
T=$2
say_i18n() { echo "$2"; }
readlink() { case "$1" in -f) echo "$2";; *) echo same-namespace;; esac; }
sleep() { :; }
sm() {
    if [ "$1" = unmount ]; then echo "$2" >> "$T/unmounts"; touch "$T/released"; return 0; fi
    echo 'public:8,1 mounted OTHER'
    echo 'public:179,34 mounted OTHER_PARTITION'
    if [ -f "$T/released" ]; then echo "public:179,33 $AFTER CARD"; else echo "public:179,33 $BEFORE CARD"; fi
}
tf_release /dev/block/mmcblk1p1
'''
                r = run_shell(code, path, root, env=dict(os.environ, BEFORE=before, AFTER=after))
                self.assertEqual(r.returncode == 0, safe and not residue, r.stdout + r.stderr)
                if before in ('mounted', 'mounted_ro'):
                    self.assertEqual((root / 'unmounts').read_text(), 'public:179,33\n')
                else:
                    self.assertFalse((root / 'unmounts').exists())


class PayloadManifest(unittest.TestCase):
    def test_metadata_hashes_requirements_and_unsafe_paths(self):
        spec = importlib.util.spec_from_file_location('tf_manifest', TOOLS / 'tf-payload-manifest.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for unsafe in (False, True):
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'boot-linux.img').write_bytes(b'boot')
                (root / 'android-bootchain.sh').write_bytes(b'checker')
                (root / 'bootchain.sh').write_bytes(b'checker')
                with tarfile.open(root / 'mu300-openwrt.tar.gz', 'w:gz') as archive:
                    for name in ('./bin/busybox', './sbin/procd', './sbin/init', './etc/uci-defaults/90-mu300', './etc/init.d/mu300-vendor'):
                        m = tarfile.TarInfo(name); m.size = 4
                        archive.addfile(m, io.BytesIO(b'test'))
                    if unsafe:
                        m = tarfile.TarInfo('../escape'); archive.addfile(m)
                if unsafe:
                    with self.assertRaises(ValueError): module.manifest(root)
                    continue
                module.manifest(root)
                kib, inodes = map(int, (root / 'rootfs.requirements').read_text().split())
                self.assertGreater(kib, 262144)
                self.assertGreater(inodes, 16384)
                for line in (root / 'payload.sha256').read_text().splitlines():
                    digest, name = line.split()
                    self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())

    def test_existing_built_rootfs_is_compatible(self):
        rootfs = TOP / 'openwrt/mu300-openwrt-tf-7.2-rootfs.tar.gz'
        if not rootfs.exists(): self.skipTest('no local built rootfs')
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / 'mu300-openwrt.tar.gz').symlink_to(rootfs)
            (stage / 'boot-linux.img').write_bytes(b'test-boot')
            shutil.copy(TOOLS / 'android-bootchain.sh', stage / 'android-bootchain.sh')
            shutil.copy(TOOLS.parent / 'android/magisk/mu300-linux-switch/bootchain.sh', stage / 'bootchain.sh')
            r = subprocess.run(['python3', str(TOOLS / 'tf-payload-manifest.py'), tmp],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


@unittest.skipUnless(shutil.which('mke2fs') and shutil.which('dumpe2fs'), 'e2fsprogs required')
class SparseFormat(unittest.TestCase):
    def test_full_capacity_512_mib_and_128_gib(self):
        # A regular sparse file under the private temporary directory, never
        # a loop device or mount. Verifies real ext4 geometry and inode count.
        for size in (512 * 1024**2, 128 * 1024**3):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as tmp:
                disk = Path(tmp) / 'card.img'
                with disk.open('wb') as stream: stream.truncate(size)
                args = ['mke2fs', '-t', 'ext4', '-F', '-b', '4096', '-m', '0', '-i', '1048576']
                if size // 1048576 < 21024: args += ['-N', '21024']
                r = subprocess.run(args + ['-E', 'lazy_itable_init=1,lazy_journal_init=1,nodiscard', '-L', 'mu300sd', str(disk)],
                                   capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr)
                r = subprocess.run(['dumpe2fs', '-h', str(disk)], env=dict(os.environ, LC_ALL='C'),
                                   capture_output=True, text=True, check=True, timeout=10)
                fields = dict(line.split(':', 1) for line in r.stdout.splitlines() if ':' in line)
                self.assertEqual(int(fields['Block count']) * int(fields['Block size']), size)
                self.assertGreaterEqual(int(fields['Inode count']), 21024)
                self.assertEqual(fields['Filesystem volume name'].strip(), 'mu300sd')


@unittest.skipUnless(BB, 'BusyBox required')
class BoundedStages(unittest.TestCase):
    def test_corrupt_payload_fails_preflight_before_storage_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(TOOLS / 'tf-storage.sh', root / 'tf-storage.sh')
            (root / 'mu300-install.env').write_text('SD_MODE=1\n')
            good = b'original-payload'
            (root / 'mu300-openwrt.tar.gz').write_bytes(b'corrupted-payload')
            (root / 'payload.sha256').write_text(hashlib.sha256(good).hexdigest() + '  mu300-openwrt.tar.gz\n')
            r = subprocess.run([BB, 'sh', str(TOOLS / 'tf-install-worker.sh'), '--preflight'],
                               env=dict(os.environ, MU300_PAYLOAD_DIR=tmp, MU300_INSTALL_TMP=tmp,
                                        MU300_BUSYBOX=BB), capture_output=True, text=True, timeout=10)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('FAILED', r.stdout + r.stderr)
            # SD_DEV and BOOTDEV are deliberately unset. Reaching any device
            # check would produce a nounset failure instead of the checksum error.
            self.assertNotIn('parameter not set', r.stderr)

    def test_success_failure_and_timeout(self):
        for command, status in [('echo stage-complete', 0), ('echo injected-failure; exit 7', 1), ('sleep 30', 124)]:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                start = time.monotonic()
                r = subprocess.run([BB, 'sh', str(TOOLS / 'tf-stage.sh'), 'test', '2', 'sh', '-c', command],
                                   env=dict(os.environ, MU300_BUSYBOX=BB, MU300_TF_STATE=tmp),
                                   capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode, status, r.stdout + r.stderr)
                self.assertLess(time.monotonic() - start, 8)
                self.assertEqual((Path(tmp) / 'reboot-required').exists(), status == 124)

    def test_worker_gates_boot_and_misc_and_blocks_retry(self):
        stages = ['preflight', 'vendor-preflight', 'staging-space', 'rootfs', 'boot-write', 'boot-readback', 'arm-slot']
        source = (TOOLS / 'tf-install-worker.sh').read_text()
        for fail in stages + ['none']:
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                # Replace only command execution with a recorded fault; retain
                # real orchestration, set -e, boot-id lock and log allocation.
                shim = '''tf_step() { echo "$1" >> "$T/stages"; [ "$1" != "$FAIL" ]; }
tf_die() { echo "$1"; return 1; }
'''
                worker = root / 'worker.sh'
                worker.write_text(source.replace('. "$P/tf-storage.sh"', shim))
                env = dict(os.environ, MU300_BUSYBOX=BB, MU300_PAYLOAD_DIR=tmp,
                           MU300_INSTALL_TMP=tmp, FAIL=fail)
                r = subprocess.run([BB, 'sh', str(worker)], env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode == 0, fail == 'none', r.stdout + r.stderr)
                expected = stages if fail == 'none' else stages[:stages.index(fail) + 1]
                self.assertEqual((root / 'stages').read_text().splitlines(), expected)
                if fail != 'none':
                    retry = subprocess.run([BB, 'sh', str(worker)], env=env, capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(retry.returncode, 0)
                    self.assertEqual((root / 'stages').read_text().splitlines(), expected)


class InitBounds(unittest.TestCase):
    def test_issue65_boundary_never_probes(self):
        source = (TOP / 'boot/init').read_text()
        functions = source[source.index('root_region_valid()'):source.index('# A TF-only image')]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'mmcblk0p1'; p.mkdir()
            (root / 'size').write_text('61079552')
            (p / 'start').write_text('2048')
            (p / 'size').write_text(str(61075456 - 2048))
            functions = functions.replace('/sys/block/mmcblk0', str(root))
            for offset, good in [(31272730624, False), (27762098176, False), (61075456 * 512, True), (-1, False)]:
                r = run_shell(functions + '\nroot_region_valid "$1"', offset)
                self.assertEqual(r.returncode == 0, good, r.stdout + r.stderr)
            # No dd/losetup can execute for the exact reported out-of-disk offset.
            r = run_shell(functions + '''
dd() { echo UNEXPECTED_IO; return 1; }
losetup() { echo UNEXPECTED_IO; return 1; }
is_mu300root 31272730624
''')
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn('UNEXPECTED_IO', r.stdout)

    def test_tf_marker_suppresses_emmc_fallback(self):
        source = (TOP / 'boot/init').read_text()
        segment = source[source.index('internal_root='):source.index('mkdir -p /newroot')]
        for target, should_probe in [('sd', False), ('', True)]:
            code = '''root_target=$1; root_mounted=0; sd_root=; ROOT_OFFSET=0
log() { :; }
find_root_offset() { echo PROBED >&2; return 1; }
''' + segment
            r = run_shell(code, target)
            self.assertEqual('PROBED' in r.stderr, should_probe)


class RootfsTransaction(unittest.TestCase):
    def test_real_extract_and_finalization_fail_closed(self):
        # Only block-device/vold/mount/mkfs calls are mocked. Run the actual
        # tar extraction, .new publication, checksums and success-marker logic.
        for fault in ('none', 'extract', 'unmount', 'checksum'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); payload = root / 'payload'; payload.mkdir()
                fakebin = root / 'bin'; fakebin.mkdir()
                trace = root / 'trace'
                def stub(name, body):
                    p = fakebin / name
                    p.write_text('#!/bin/sh\n' + body + '\n'); p.chmod(0o755)
                    return p
                stub('mount', 'echo mount >> "$TRACE"')
                stub('umount', 'echo umount >> "$TRACE"; [ "$FAULT" != unmount ]')
                stub('df', 'echo "Filesystem 1K-blocks Used Available Use% Mounted"; echo "fixture 9999999 1 9999998 1% /"')
                stub('blockdev', 'echo 268435456')
                mkfs = stub('mke2fs', 'echo format >> "$TRACE"')
                disk = root / 'card'
                sb = bytearray(4096); sb[1080:1082] = bytes.fromhex('53ef'); sb[1144:1151] = b'mu300sd'
                disk.write_bytes(sb)
                (payload / 'mu300-install.env').write_text(f'''SD_MODE=1
SD_DEV={disk}
FORMAT=1
OSES=openwrt
WIPE_LEGACY=0
UPDATE=0
BOOT_OS=openwrt
DEFAULT_LINUX=1
BOOT_ATTEMPTS=5
IMPORT_HOTSPOT=0
KERNEL=7.2
PWHASH=''
''')
                (payload / 'rootfs.requirements').write_text('500000 20000\n')
                files = {'sbin/init': b'init', 'sbin/procd': b'procd', 'bin/busybox': b'busybox',
                         'etc/init.d/mu300-vendor': b'vendor', 'etc/config/network': b'network',
                         'opt/mu300/android/dev-properties/stale': b'build-device'}
                vendor = root / 'vendor'; vf = vendor / 'opt/mu300/android/dev-properties/current'
                vf.parent.mkdir(parents=True); vf.write_bytes(b'current-device')
                (root / 'vendor.sha256').write_text(hashlib.sha256(vf.read_bytes()).hexdigest() +
                                                  '  ./opt/mu300/android/dev-properties/current\n')
                with tarfile.open(payload / 'mu300-openwrt.tar.gz', 'w:gz') as archive:
                    for name, data in files.items():
                        m = tarfile.TarInfo(name); m.mode = 0o755; m.size = len(data)
                        archive.addfile(m, io.BytesIO(data))
                if fault == 'extract':
                    (payload / 'mu300-openwrt.tar.gz').write_bytes(b'not a gzip')
                digest = hashlib.sha256(files['sbin/procd']).hexdigest()
                if fault == 'checksum': digest = '0' * 64
                (payload / 'rootfs-critical.sha256').write_text(f'{digest}  sbin/procd\n')
                shutil.copy(TOOLS / 'tf-storage.sh', payload / 'tf-storage.sh')
                code = (TOOLS / 'android-install.sh').read_text()
                code = code.replace('[ -b "$R" ]', '[ -f "$R" ]')
                code = code.replace('tf_release "$R"', 'echo release >> "$TRACE"')
                code = code.replace('/system/bin/mke2fs', str(mkfs))
                script = root / 'installer.sh'; script.write_text(code)
                env = dict(os.environ, MU300_INSTALL_TMP=tmp, MU300_PAYLOAD_DIR=str(payload),
                           MU300_TF_STATE=tmp, MU300_KEEP_PAYLOAD='1', TRACE=str(trace), FAULT=fault,
                           MU300_PREPARED_VENDOR=str(vendor),
                           PATH=str(fakebin) + os.pathsep + os.environ['PATH'])
                r = subprocess.run(['sh', str(script)], env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode == 0, fault == 'none', r.stdout + r.stderr)
                self.assertEqual('MU300-INSTALL-OK' in r.stdout, fault == 'none', r.stdout)
                events = trace.read_text().splitlines()
                if fault == 'none':
                    self.assertEqual(events, ['release', 'format', 'mount', 'umount', 'mount', 'umount'])
                    self.assertTrue((root / 'mu300root/openwrt/sbin/procd').exists())
                    self.assertFalse((root / 'mu300root/openwrt.new').exists())
                    self.assertFalse((root / 'mu300root/openwrt/opt/mu300/android/dev-properties/stale').exists())
                    self.assertTrue((root / 'mu300root/openwrt/opt/mu300/android/dev-properties/current').exists())
                elif fault in ('extract', 'checksum'):
                    self.assertNotIn('umount', events)  # no error-path global sync/unmount into a bad card
                    self.assertFalse((root / 'mu300root/openwrt').exists())


if __name__ == '__main__':
    unittest.main()
