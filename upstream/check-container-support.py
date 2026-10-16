#!/usr/bin/env python3
"""Verify KVM/container/eBPF capabilities and complete TF/kernel module sets."""
import argparse
import hashlib
import re
import runpy
import tarfile
from pathlib import Path


BUILTIN = '''VIRTUALIZATION KVM IKCONFIG IKCONFIG_PROC CGROUPS MEMCG BLK_CGROUP
CGROUP_SCHED CGROUP_PIDS CPUSETS CGROUP_BPF CFS_BANDWIDTH BLK_DEV_THROTTLING
NAMESPACES UTS_NS IPC_NS USER_NS PID_NS NET_NS SECCOMP SECCOMP_FILTER
POSIX_MQUEUE VETH BRIDGE TUN OVERLAY_FS NF_CONNTRACK NF_NAT NF_TABLES NFT_COMPAT
NETFILTER_XT_MATCH_CONNTRACK NETFILTER_XT_TARGET_MASQUERADE
BPF BPF_SYSCALL BPF_JIT BPF_EVENTS BPF_STREAM_PARSER BPF_UNPRIV_DEFAULT_OFF
DEBUG_INFO_BTF DEBUG_INFO_BTF_MODULES KALLSYMS_ALL FTRACE FUNCTION_TRACER
FUNCTION_GRAPH_TRACER DYNAMIC_FTRACE FTRACE_SYSCALLS KPROBES KPROBE_EVENTS
UPROBES UPROBE_EVENTS PERF_EVENTS ARM_PMU'''.split()
MODULES = {
    'VHOST_NET': 'vhost_net', 'VSOCKETS': 'vsock', 'VHOST_VSOCK': 'vhost_vsock',
    'BRIDGE_NETFILTER': 'br_netfilter', 'NETFILTER_XT_MATCH_ADDRTYPE': 'xt_addrtype',
    'NETFILTER_XT_MATCH_IPVS': 'xt_ipvs', 'NETFILTER_XT_MARK': 'xt_mark',
    'IP_VS': 'ip_vs', 'IP_VS_RR': 'ip_vs_rr', 'IP_VS_WRR': 'ip_vs_wrr',
    'IP_VS_SH': 'ip_vs_sh', 'VXLAN': 'vxlan', 'IPVLAN': 'ipvlan',
    'MACVTAP': 'macvtap', 'BINFMT_MISC': 'binfmt_misc', 'FUSE_FS': 'fuse',
    'ARM_SPRD_CPUFREQ_V2': 'sprd_cpufreq_v2_driver',
    'NETFILTER_XT_NAT': 'xt_nat',
    'NET_SCH_FQ': 'sch_fq', 'NET_SCH_HTB': 'sch_htb',
    'NET_SCH_TBF': 'sch_tbf', 'NET_SCH_PRIO': 'sch_prio',
    'NET_SCH_NETEM': 'sch_netem', 'NET_CLS_U32': 'cls_u32',
    'NET_CLS_FLOWER': 'cls_flower', 'NET_CLS_MATCHALL': 'cls_matchall',
    'NET_ACT_BPF': 'act_bpf', 'NET_ACT_MIRRED': 'act_mirred',
    'NET_ACT_POLICE': 'act_police', 'NET_ACT_GACT': 'act_gact',
    'NET_ACT_SKBEDIT': 'act_skbedit', 'NET_ACT_CT': 'act_ct',
    'IFB': 'ifb', 'NETLINK_DIAG': 'netlink_diag',
    'UNIX_DIAG': 'unix_diag', 'PACKET_DIAG': 'af_packet_diag',
    'IPVTAP': 'ipvtap', 'GENEVE': 'geneve',
}

# PR #228: optional features must ship their dependency modules too.
MODULES.update({
    'VIRTIO_PCI': 'virtio_pci',
    'VIRTIO_NET': 'virtio_net',
    'VIRTIO_BLK': 'virtio_blk',
    'VIRTIO_CONSOLE': 'virtio_console',
    'HW_RANDOM_VIRTIO': 'virtio_rng',
    'VIRTIO_BALLOON': 'virtio_balloon',
    'VIRTIO_INPUT': 'virtio_input',
    'VIRTIO_FS': 'virtiofs',
    'VIRTIO_VSOCKETS': 'vmw_vsock_virtio_transport',
    'NET_9P': '9pnet',
    'NET_9P_VIRTIO': '9pnet_virtio',
    '9P_FS': '9p',
    'VHOST_SCSI': 'vhost_scsi',
    'USBIP_CORE': 'usbip_core',
    'USBIP_HOST': 'usbip_host',
    'USBIP_VHCI_HCD': 'vhci_hcd',
    'USB_VIDEO_CLASS': 'uvcvideo',
    'USB_NET_AX8817X': 'asix',
    'NFS_FS': 'nfs',
    'NFSD': 'nfsd',
    'CIFS': 'cifs',
    'XFS_FS': 'xfs',
    'DM_CACHE': 'dm_cache',
    'DM_WRITECACHE': 'dm_writecache',
    'DM_MULTIPATH': 'dm_multipath',
    'DM_INTEGRITY': 'dm_integrity',
    'DM_MIRROR': 'dm_mirror',
    'MD_RAID456': 'raid456',
})


def config_check(path):
    config = dict(line.split('=', 1) for line in path.read_text().splitlines()
                  if line.startswith('CONFIG_') and '=' in line)
    for key in BUILTIN:
        if config.get('CONFIG_' + key) != 'y':
            raise ValueError(f'CONFIG_{key}=y missing in built kernel.config; rebuild kernel')
    for key in MODULES:
        if config.get('CONFIG_' + key) not in ('y', 'm'):
            raise ValueError(f'CONFIG_{key} missing in built kernel.config; rebuild kernel')
    if config.get('CONFIG_ARM_SPRD_CPUFREQ_V2') != 'm':
        raise ValueError('CONFIG_ARM_SPRD_CPUFREQ_V2=m required for boot voltage profiles; rebuild kernel')
    runpy.run_path(str(Path(__file__).with_name('audit-bundle.py')))['expanded_check'](config, Path(__file__).with_name('mu300-mainline.config'))
    return config


def check_hashes(out, manifest):
    names = set()
    for line in (out / manifest).read_text().splitlines():
        digest, name = line.split(None, 1)
        name = name.lstrip('* ')
        if Path(name).is_absolute() or '..' in Path(name).parts or name in names:
            raise ValueError(f'invalid/duplicate manifest path: {name}')
        if hashlib.sha256((out / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'{name} no longer matches {manifest}; rebuild it')
        names.add(name)
    return names


def check(out):
    config = config_check(out / 'kernel.config')
    for name in ('modules.builtin', 'modules.builtin.modinfo'):
        if not (out / name).is_file() or not (out / name).stat().st_size:
            raise ValueError(f'{name} missing; built-in module indexes must ship too')
    if check_hashes(out, 'kernel.sha256') != {'Image', 'kernel.config'}:
        raise ValueError('kernel.sha256 must tie Image to kernel.config')
    files = {f'modules/{p.name}' for p in (out / 'modules').glob('*.ko')}
    if not files or check_hashes(out, 'modules.sha256') != files | {'Image', 'kernel.config'}:
        raise ValueError('module manifest is empty/incomplete or stale; rebuild modules')
    version = re.search(rb'Linux version ([^\s\x00]+)', (out / 'Image').read_bytes())
    if not version:
        raise ValueError('cannot identify Image kernel release')
    for name in files:
        vermagic = re.search(rb'vermagic=([^\s\x00]+)', (out / name).read_bytes())
        if not vermagic or vermagic[1] != version[1]:
            raise ValueError(f'{name} vermagic does not match Image')
    runpy.run_path(str(Path(__file__).with_name('audit-bundle.py')))['audit'](out)
    normalized = {name.replace('-', '_') for name in files}
    if len(normalized) != len(files):
        raise ValueError('module names collide after hyphen/underscore normalization')
    for key, name in MODULES.items():
        if config['CONFIG_' + key] == 'm' and f'modules/{name}.ko' not in normalized:
            raise ValueError(f'{name}.ko missing; kernel support was configured but not packaged')
    for name in (out / 'modules.in-tree').read_text().splitlines():
        if f'modules/{name}' not in files:
            raise ValueError(f'in-tree dependency {name} missing')
    return version[1].decode('ascii')


def check_rootfs(out, archive, release):
    prefix = f'lib/modules/{release}/'
    expected = {prefix + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (out / 'modules').glob('*.ko')}
    for name in ('modules.builtin', 'modules.builtin.modinfo'):
        expected[prefix + name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    # Read as a stream, never unpack a tar into the host filesystem.
    seen = set()
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            name = member.name.removeprefix('./')
            if name not in expected:
                if name.startswith(prefix) and name.endswith('.ko'):
                    raise ValueError(f'rootfs contains unexpected module: {name}')
                continue
            if name in seen or not member.isfile():
                raise ValueError(f'rootfs duplicate/non-file module entry: {name}')
            data = tar.extractfile(member)
            if hashlib.sha256(data.read()).hexdigest() != expected[name]:
                raise ValueError(f'rootfs module/index differs from build: {name}')
            seen.add(name)
    if seen != set(expected):
        raise ValueError('rootfs missing built modules/indexes: ' + ', '.join(sorted(set(expected) - seen)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--config-only', action='store_true')
    parser.add_argument('--rootfs', type=Path)
    args = parser.parse_args()
    try:
        if args.config_only:
            config_check(args.output)
        else:
            release = check(args.output)
            if args.rootfs:
                check_rootfs(args.output, args.rootfs, release)
    except (OSError, ValueError) as error:
        parser.exit(1, f'KVM/container/eBPF build check: {error}\n')
    print('KVM/container/eBPF build checks passed (runtime verification still required)')
