"""Fail closed when KVM is only requested, or optional modules never get shipped."""
import hashlib
import gzip
import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

spec = importlib.util.spec_from_file_location('container_support', TOP / 'upstream/check-container-support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


class ContainerSupport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        (self.out / 'modules').mkdir()
        for name in ('modules.builtin', 'modules.builtin.modinfo'):
            (self.out / name).write_bytes(b'builtin metadata')
        self.config = {key: 'y' for key in support.BUILTIN}
        self.config.update({key: 'm' for key in support.MODULES})
        import re
        fragment = (TOP/'upstream/mu300-mainline.config').read_text()
        self.config.update({k.removeprefix('CONFIG_'):v for k,v in re.findall(r'^(CONFIG_\w+)=(.*)$', fragment[fragment.index('# Adapted from MU300 PR #228'):], re.M)})
        (self.out / 'Image').write_bytes(b'Linux version 6.18.54 test Image')
        for name in support.MODULES.values():
            (self.out / 'modules' / f'{name}.ko').write_bytes(name.encode() + b'\0vermagic=6.18.54 SMP\0')
        (self.out / 'modules/dependency.ko').write_bytes(b'needed dependency\0vermagic=6.18.54 SMP\0')
        self.write_config()
        (self.out / 'modules.in-tree').write_text('\n'.join(p.name for p in (self.out / 'modules').glob('*.ko')) + '\n')
        self.manifests()

    def write_config(self):
        config = ''.join(f'CONFIG_{k}={v}\n' for k, v in self.config.items())
        (self.out / 'kernel.config').write_text(config)
        (self.out / 'Image').write_bytes(b'Linux version 6.18.54 test Image' + b'IKCFG_ST' + gzip.compress(config.encode()) + b'IKCFG_ED')

    def manifests(self):
        for manifest, names in [('kernel.sha256', ['Image', 'kernel.config']),
                                ('modules.sha256', ['Image', 'kernel.config'] +
                                 sorted(f'modules/{p.name}' for p in (self.out / 'modules').glob('*.ko')))]:
            (self.out / manifest).write_text(''.join(
                f'{hashlib.sha256((self.out / n).read_bytes()).hexdigest()}  {n}\n' for n in names))

    def test_complete_output_passes(self):
        support.check(self.out)

    def test_config_without_kvm_cannot_ship(self):
        self.config['KVM'] = 'n'
        self.write_config()
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'KVM'):
            support.check(self.out)

    def test_incomplete_ebpf_or_tracing_cannot_ship(self):
        for feature in ('BPF_JIT', 'DEBUG_INFO_BTF', 'DEBUG_INFO_BTF_MODULES',
                        'PERF_EVENTS', 'KPROBE_EVENTS', 'FUNCTION_GRAPH_TRACER',
                        'BPF_UNPRIV_DEFAULT_OFF'):
            with self.subTest(feature=feature):
                self.config[feature] = 'n'
                self.write_config()
                self.manifests()
                with self.assertRaisesRegex(ValueError, feature):
                    support.check(self.out)
                self.config[feature] = 'y'

    def test_bpf_network_module_cannot_be_omitted(self):
        (self.out / 'modules/act_bpf.ko').unlink()
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'act_bpf'):
            support.check(self.out)

    def test_btf_build_dependencies_and_no_early_debug_modules(self):
        self.assertIn('pahole', (TOP/'upstream/Dockerfile').read_text())
        self.assertIn('--strip-debug', (TOP/'upstream/build-modules.sh').read_text())
        self.assertIn('BTF missing from built module', (TOP/'upstream/build-modules.sh').read_text())
        self.assertIn('BTF missing from the linked kernel', (TOP/'upstream/build.sh').read_text())
        for script in ('build.sh', 'build-modules.sh'):
            btf_checks = [line for line in (TOP/'upstream'/script).read_text().splitlines()
                          if 'readelf' in line and '|' in line]
            self.assertTrue(btf_checks)
            for line in btf_checks:
                self.assertNotIn('grep -Eq', line)  # SIGPIPE under pipefail
                self.assertIn('>/dev/null', line)
        early = (TOP/'upstream/module-order.txt').read_text()
        for name in ('act_bpf', 'sch_netem', 'ifb', 'ipvtap', 'geneve'):
            self.assertNotIn(name, early)

    def test_old_builtin_cpufreq_cannot_silently_omit_voltage(self):
        self.config['ARM_SPRD_CPUFREQ_V2'] = 'y'
        self.write_config()
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'boot voltage profiles'):
            support.check(self.out)

    def test_missing_builtin_index_rejected_before_any_packaging(self):
        (self.out / 'modules.builtin').unlink()
        with self.assertRaisesRegex(ValueError, 'modules.builtin missing'):
            support.check(self.out)

    def test_missing_required_module_even_if_manifest_is_regenerated(self):
        (self.out / 'modules/vhost_net.ko').unlink()
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'vhost_net'):
            support.check(self.out)

    def test_missing_non_shortlisted_dependency(self):
        (self.out / 'modules/dependency.ko').unlink()
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'dependency'):
            support.check(self.out)

    def test_changed_image_or_config_invalidates_old_modules(self):
        (self.out / 'Image').write_bytes(b'new build same release')
        # A kernel-only rebuild refreshes kernel.sha256, never modules.sha256.
        (self.out / 'kernel.sha256').write_text(''.join(
            f'{hashlib.sha256((self.out / n).read_bytes()).hexdigest()}  {n}\n'
            for n in ['Image', 'kernel.config']))
        with self.assertRaisesRegex(ValueError, 'modules.sha256'):
            support.check(self.out)

    def test_modified_or_extra_module_rejected(self):
        (self.out / 'modules/vhost_net.ko').write_bytes(b'old module')
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            support.check(self.out)
        self.manifests()
        (self.out / 'modules/stale.ko').write_bytes(b'stale')
        with self.assertRaisesRegex(ValueError, 'stale'):
            support.check(self.out)

    def test_hyphen_underscore_collision_rejected(self):
        (self.out / 'modules/vhost-net.ko').write_bytes(b'alias\0vermagic=6.18.54 SMP\0')
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'collide'):
            support.check(self.out)

    def test_mixed_kernel_modules_rejected_even_with_fresh_hashes(self):
        (self.out / 'modules/vhost_net.ko').write_bytes(b'vermagic=7.2.8 SMP\0')
        self.manifests()
        with self.assertRaisesRegex(ValueError, 'vermagic'):
            support.check(self.out)

    def test_fragment_and_packaging_routes_keep_support(self):
        support.config_check(TOP / 'upstream/mu300-mainline.config')
        for path in ['upstream/make-bundle.sh', 'tools/build-openwrt-tf-magisk.sh',
                     'openwrt/build-rootfs.sh']:
            self.assertIn('check-container-support.py', (TOP / path).read_text())
        builder = (TOP / 'upstream/build-modules.sh').read_text()
        self.assertIn('INSTALL_MOD_STRIP=1', builder)
        self.assertIn('modules_install', builder)
        self.assertIn('modules.in-tree.names', builder)
        early = (TOP / 'upstream/module-order.txt').read_text()
        self.assertNotIn('vhost_net', early)
        self.assertNotIn('br_netfilter', early)

    def test_final_rootfs_requires_identical_modules_and_builtin_indexes(self):
        for name in ('modules.builtin', 'modules.builtin.modinfo'):
            (self.out / name).write_bytes(b'builtin metadata')
        archive = self.out / 'rootfs.tar.gz'
        paths = list((self.out / 'modules').glob('*.ko')) + [
            self.out / 'modules.builtin', self.out / 'modules.builtin.modinfo']
        def write_tar(skip=None, damage=None):
            with tarfile.open(archive, 'w:gz') as tar:
                for path in paths:
                    if path.name == skip:
                        continue
                    data = b'wrong' if path.name == damage else path.read_bytes()
                    info = tarfile.TarInfo('./lib/modules/6.18.54/' + path.name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
        write_tar()
        support.check_rootfs(self.out, archive, '6.18.54')
        write_tar(skip='modules.builtin')
        with self.assertRaisesRegex(ValueError, 'missing'):
            support.check_rootfs(self.out, archive, '6.18.54')
        write_tar(damage='vhost_net.ko')
        with self.assertRaisesRegex(ValueError, 'differs'):
            support.check_rootfs(self.out, archive, '6.18.54')
