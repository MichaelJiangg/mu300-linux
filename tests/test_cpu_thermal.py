"""Thermal capability, safety boundaries and installation coverage."""
import shutil
import subprocess
import unittest
from helpers import TOP

APP = TOP / 'openwrt/luci-app-mu300'

class CpuThermal(unittest.TestCase):
    def test_module_uses_factory_sensor_trips_and_no_new_worker(self):
        source = (TOP/'upstream/modules/mu300_thermal/mu300_thermal.c').read_text()
        for token in ('thmzone-cells', 'thermal_zone_get_zone_by_name', 'devm_thermal_of_zone_register', '-EPROBE_DEFER', 'hottest = max'):
            self.assertIn(token, source)
        for token in ('kthread_run', 'schedule_delayed_work', '.set_trips', '110000', '85000'):
            self.assertNotIn(token, source)
        self.assertIn('mu300_thermal', (TOP/'upstream/build-modules.sh').read_text())
        self.assertNotIn('mu300_thermal', (TOP/'upstream/module-order.txt').read_text())
        self.assertIn('mu300_thermal.ko', (TOP/'rootfs/overlay/opt/mu300/bin/extra-modules').read_text())

    def test_installer_requires_backend_and_fresh_module(self):
        for name in ('tools/build-openwrt-tf-magisk.sh','tools/make-release.sh'):
            self.assertIn('./usr/libexec/unisoc-modem/cpu-thermal.uc', (TOP/name).read_text())
        for name in ('upstream/make-bundle.sh','tools/build-openwrt-tf-magisk.sh'):
            self.assertIn('sprd_wlan_combo wcn_bsp mu300_thermal', (TOP/name).read_text())

    def test_generic_ui_and_readonly_critical(self):
        source = (APP/'root/usr/libexec/unisoc-modem/cpu-thermal.uc').read_text()
        self.assertIn("writable:kind=='passive'", source)
        self.assertIn('t.temp-10000', source)
        self.assertNotIn('thermal_zone19', source)
        self.assertNotIn('AT+', source)
        view = (APP/'htdocs/luci-static/resources/view/mu300/cpu.js').read_text()
        for token in ("controlsFor('frequency'", "controlsFor('thermal'", 'payload.thermal', 'throttles_cpu','hysteresis','reset: true','checkValidity','self.thermalLive'):
            self.assertIn(token, view)
        self.assertIn('root.append(section, thermalSection)', view)
        self.assertIn('thermal_persist', view)
        translations = (APP/'htdocs/luci-static/resources/mu300/common.js').read_text()
        for label in ('温控管理','降频触发温度','被动温控起点','临界保护温度','恢复启动基线？','温控配置回读不一致'):
            self.assertIn(label, translations)

    @unittest.skipUnless(shutil.which('ucode') and shutil.which('jsonfilter'), 'run cpu_thermal_fixture.sh in OpenWrt container')
    def test_fake_sysfs(self):
        subprocess.run(['sh',str(TOP/'tests/cpu_thermal_fixture.sh'),str(APP/'root/usr/libexec/unisoc-modem/cpu.uc')],check=True,timeout=30)
