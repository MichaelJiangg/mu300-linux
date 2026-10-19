"""Boot-only voltage ABI, packaging and standalone capability boundaries."""
import json
import shutil
import subprocess
import unittest
from helpers import TOP, ShellTest

APP = TOP / 'openwrt/luci-app-mu300'

class CpuVoltage(unittest.TestCase):
    def test_firmware_quantization_roundtrip(self):
        for uv in range(-50000, 25001, 3125):
            magnitude = abs(uv) // 1000
            decoded = ((magnitude * 1000 + 3124) // 3125) * 3125
            self.assertEqual(-decoded if uv < 0 else decoded, uv)
            self.assertLessEqual(magnitude, 100)

    def test_boot_only_kernel_and_loader(self):
        driver = (TOP/'upstream/port/drivers/cpufreq/sprd-cpufreq-v2-driver.c').read_text()
        self.assertIn('voltage_offset_count, 0444', driver)
        self.assertIn('.suppress_bind_attrs = true', driver)
        self.assertNotIn('module_exit(', driver)
        self.assertIn('if (firmware_initialized)', driver)
        self.assertIn('CONFIG_ARM_SPRD_CPUFREQ_V2=m', (TOP/'upstream/mu300-mainline.config').read_text())
        self.assertNotIn('sprd-cpufreq-v2', (TOP/'upstream/module-order.txt').read_text())
        loader = (TOP/'rootfs/overlay/opt/mu300/bin/cpu-voltage-platform').read_text()
        self.assertLess(loader.index('sync #'), loader.index('insmod "$ko"'))
        self.assertIn('for slot in a b', loader)
        self.assertIn('flock -x 9', loader)

    def test_permissions_and_build_contract(self):
        acl=json.loads((APP/'root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())['luci-app-mu300']
        self.assertIn('cpu_voltage_get', acl['read']['ubus']['mu300dash'])
        self.assertNotIn('cpu_voltage_save', acl['read']['ubus']['mu300dash'])
        for script in ('build-openwrt-tf-magisk.sh','make-release.sh'):
            text=(TOP/'tools'/script).read_text()
            for entry in ('cpu-voltage.uc', 'cpu-voltage-platform', 'S08mu300-cpu-driver', 'K89unisoc-cpu'):
                self.assertIn(entry,text)
        init=(APP/'root/etc/init.d/unisoc-cpu').read_text()
        self.assertIn('shutdown()',init)
        self.assertNotIn('stop()',init)

    @unittest.skipUnless(shutil.which('ucode') and shutil.which('jsonfilter'), 'requires OpenWrt ucode/jsonfilter; also run cpu_voltage_fixture.sh in the OpenWrt container')
    def test_isolated_profiles(self):
        subprocess.run(['sh',str(TOP/'tests/cpu_voltage_fixture.sh'),str(APP/'root/usr/libexec/unisoc-modem/cpu-voltage.uc')],check=True,timeout=30)

class EarlyVoltageDiscovery(ShellTest):
    def test_partition_labels_work_before_vendor_symlinks(self):
        source=(TOP/'rootfs/overlay/opt/mu300/bin/cpu-voltage-platform').read_text()
        check=source[source.index('supported() {'):source.index('case ${1:-load}')]
        # Redirect every filesystem read to regular fake devices; no actual
        # partitions, module loading, or hash bypass in production code.
        check=check.replace('/sys/',str(self.tmp)+'/sys/').replace('/dev/',str(self.tmp)+'/dev/').replace('[ -b ', '[ -f ')
        # BusyBox standalone ash may resolve its hash applet before PATH.
        # Invoke this fixture's stub explicitly, never a real firmware hash.
        check=check.replace('sha256sum "$part"', '"$STUBLOG/stubs/sha256sum" "$part"')
        compatible=self.tmp/'sys/firmware/devicetree/base/compatible'
        compatible.parent.mkdir(parents=True)
        compatible.write_bytes(b'zte,f50\0sprd,ums9620\0')
        (self.tmp/'dev').mkdir()
        for i,slot in enumerate(('a','b'),6):
            block=self.tmp/f'sys/class/block/mmcblk0p{i}'
            block.mkdir(parents=True)
            (block/'uevent').write_text(f'PARTNAME=sml_{slot}\n')
            (block/'size').write_text('2048\n')
            (self.tmp/f'dev/mmcblk0p{i}').write_bytes(b'fake firmware')
        self.stub('sha256sum','printf "%s  %s\\n" ff4782690fd805ff54fe34853ef8ee5c7e51c3259e20077c55373b50a4b259c2 "$1"')
        for shell in self.each_shell():
            r=self.sh(shell,check+'\nsupported')
            self.assertEqual(r.returncode,0,r.stderr)
        self.stub('sha256sum','printf "%s  %s\\n" 5b3183f17af9b416e71dea61e578c61824e4e1df43737a1179032f4b20466b2b "$1"')
        for shell in self.each_shell():
            self.assertEqual(self.sh(shell,check+'\nsupported').returncode,0)
        self.stub('sha256sum','printf "%s  %s\\n" f27ac16f44e6cdc87a8ee00a9b53c499c8dde0c3b92c771388e256e84ef12e70 "$1"')
        compatible.write_bytes(b'zte,u30air\0sprd,ums9620\0')
        for shell in self.each_shell():
            self.assertEqual(self.sh(shell,check+'\nsupported').returncode,0)
        # Matching chip name alone never enables an unverified SML image.
        self.stub('sha256sum','printf "%s  %s\\n" unknown "$1"')
        for shell in self.each_shell():
            self.assertNotEqual(self.sh(shell,check+'\nsupported').returncode,0)
        self.stub('sha256sum','printf "%s  %s\\n" 5b3183f17af9b416e71dea61e578c61824e4e1df43737a1179032f4b20466b2b "$1"')
        (self.tmp/'sys/class/block/mmcblk0p7/size').write_text('4096\n')
        for shell in self.each_shell():
            self.assertNotEqual(self.sh(shell,check+'\nsupported').returncode,0)
