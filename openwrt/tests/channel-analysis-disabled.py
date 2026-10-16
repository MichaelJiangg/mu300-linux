#!/usr/bin/env python3
"""Run the installed ucode policy against isolated LuCI files (requires Docker)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[2]
PLUGIN = next((TOP / 'openwrt').glob('luci-app-*/root/usr/libexec/unisoc-modem/disable-channel-analysis'))
ASSET = PLUGIN.parents[2] / 'share/unisoc-modem/channel-analysis-disabled.js'
MENU = 'usr/share/luci/menu.d/luci-mod-status.json'
ACL = 'usr/share/rpcd/acl.d/luci-mod-status.json'
VIEW = 'www/luci-static/resources/view/status/channel_analysis.js'
ROUTE = 'admin/status/channel_analysis'
GROUP = 'luci-mod-status-channel_analysis'


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.put(MENU, {ROUTE: {'action': {'type': 'view'}}, 'admin/status/routes': {'order': 2}})
        self.put(ACL, {GROUP: {'read': {'ubus': {'iwinfo': ['scan']}}},
                       'luci-mod-network': {'read': {'ubus': {'iwinfo': ['scan', 'info']}}}})
        self.put(VIEW, "throw new Error('original scanning page');\n")
        self.put('usr/share/unisoc-modem/channel-analysis-disabled.js', ASSET.read_text())

    def put(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data) if isinstance(data, dict) else data)

    def apply(self, success=True):
        result = subprocess.run(['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', '--platform', 'linux/arm64',
            '-v', f'{self.root}:/target', '-v', f'{PLUGIN}:/policy:ro', '--entrypoint', '/usr/bin/ucode',
            'mu300-openwrt-base:25.12.5', '/policy', '/target'], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_removes_only_analysis_and_neutralizes_old_view(self):
        self.apply()
        self.assertEqual(json.loads((self.root / MENU).read_text()), {'admin/status/routes': {'order': 2}})
        self.assertEqual(json.loads((self.root / ACL).read_text()), {
            'luci-mod-network': {'read': {'ubus': {'iwinfo': ['scan', 'info']}}}})
        self.assertEqual((self.root / VIEW).read_bytes(), ASSET.read_bytes())
        for forbidden in ('rpc.declare', 'getScanList', 'poll.add'):
            self.assertNotIn(forbidden, (self.root / VIEW).read_text())

    def test_idempotent_no_rewrites(self):
        self.apply()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.apply()
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_restored_upstream_files_disabled_again(self):
        self.apply()
        self.put(MENU, {ROUTE: {'order': 7}})
        self.put(VIEW, 'upstream scan restored')
        self.apply()
        self.assertEqual(json.loads((self.root / MENU).read_text()), {})
        self.assertEqual((self.root / VIEW).read_bytes(), ASSET.read_bytes())

    def test_invalid_acl_does_not_partially_modify_menu(self):
        before = (self.root / MENU).read_bytes()
        self.put(ACL, '{invalid json')
        self.apply(success=False)
        self.assertEqual((self.root / MENU).read_bytes(), before)

    def test_missing_optional_status_package(self):
        for name in (MENU, ACL, VIEW):
            (self.root / name).unlink()
        self.apply()
        self.assertFalse((self.root / VIEW).exists())

    def test_clears_only_luci_caches(self):
        for name in ('tmp/luci-indexcache.hash', 'tmp/luci-modulecache/menu', 'tmp/other-cache'):
            self.put(name, 'cache')
        self.apply()
        self.assertFalse((self.root / 'tmp/luci-indexcache.hash').exists())
        self.assertFalse((self.root / 'tmp/luci-modulecache/menu').exists())
        self.assertTrue((self.root / 'tmp/other-cache').exists())


if __name__ == '__main__':
    unittest.main()
