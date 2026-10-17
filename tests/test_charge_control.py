"""Execute the real ucode backend in an isolated OpenWrt ARM64 container.

Set MU300_CHARGE_TEST_IMAGE to a locally built OpenWrt image with ucode/fs/uci.
No device access or external network is used.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

TOP = Path(__file__).resolve().parents[1]
ROOT = TOP/'openwrt/luci-app-mu300/root'
IMAGE = os.environ.get('MU300_CHARGE_TEST_IMAGE')


@unittest.skipUnless(IMAGE and shutil.which('docker'), 'Set MU300_CHARGE_TEST_IMAGE to run actual OpenWrt ucode')
class ChargeControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='mu300-charge-')
        cls.fixture = Path(cls.temp.name)
        cls.container = 'mu300-charge-test-'+uuid.uuid4().hex[:8]
        subprocess.run(['docker','run','-d','--name',cls.container,'--network','none','--platform','linux/arm64',
                        '-v',str(ROOT)+':/feature:ro','-v',str(cls.fixture)+':/fixture',
                        '-v',str(ROOT/'usr/libexec/unisoc-modem')+':/usr/libexec/unisoc-modem:ro',
                        IMAGE,'/bin/sleep','3600'],check=True,stdout=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker','rm','-f',cls.container],check=True,stdout=subprocess.DEVNULL)
        cls.temp.cleanup()

    def setUp(self):
        for path in self.fixture.iterdir():
            if path.is_dir():shutil.rmtree(path)
            else:path.unlink()
        self.config = self.fixture/'config'
        self.config.mkdir()
        shutil.copy2(ROOT/'etc/config/mu300-charge',self.config/'mu300-charge')
        self.sys = self.fixture/'power'
        self.charger = self.sys/'bq256xx-charger'
        self.battery = self.sys/'sc27xx-fgu'
        self.charger.mkdir(parents=True);self.battery.mkdir()
        for name,value in {'charge_type':'Fast','online':'1','status':'Charging','usb_type':'[SDP] DCP',
                           'input_current_limit':'2000000'}.items():self.write(self.charger/name,value)
        for name,value in {'capacity':'76','current_now':'500000','present':'1','calibrate':'untouched'}.items():
            self.write(self.battery/name,value)

    def write(self,path,value):path.write_text(str(value)+'\n')

    def call(self,action='get',data=None,board='u30air'):
        cmd=['docker','exec','-i',self.container,'env','MU300_CHARGE_CONFIG=/fixture/config',
             'MU300_CHARGE_SYS=/fixture/power','MU300_CHARGE_STATE=/fixture/state.json',
             'MU300_CHARGE_TYPEC=/fixture/typec','MU300_CHARGE_DEVICE='+board,
             '/usr/bin/ucode','/feature/usr/libexec/unisoc-modem/charge.uc',action]
        r=subprocess.run(cmd,input=json.dumps(data or {}),capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr)
        result=json.loads(r.stdout)
        self.assertEqual((self.charger/'input_current_limit').read_text().strip(),'2000000')
        self.assertEqual((self.battery/'calibrate').read_text().strip(),'untouched')
        return result

    def configure(self,**change):
        return self.call('configure',dict(enabled='1',start='70',stop='80',**change))

    def test_default_read_only_and_no_battery_boards(self):
        self.assertTrue(self.call()['available'])
        self.assertFalse((self.fixture/'state.json').exists())
        for board in ('f50','v50','unknown'):
            self.assertFalse(self.call(board=board)['supported'])
            self.assertEqual(self.call('pause',board=board)['error'],'charge_unavailable')
        self.assertEqual((self.charger/'charge_type').read_text().strip(),'Fast')

    def test_limit_hysteresis_and_persistence(self):
        self.write(self.battery/'capacity',90)
        self.assertTrue(self.configure()['stopped'])
        self.assertEqual((self.charger/'charge_type').read_text(),'N/A')
        self.write(self.battery/'capacity',75)
        self.assertTrue(self.call('apply')['stopped'])
        self.write(self.battery/'capacity',70)
        self.assertFalse(self.call('apply')['stopped'])
        self.assertEqual((self.charger/'charge_type').read_text(),'Fast')
        self.assertTrue(self.call()['enabled'])

    def test_manual_pause_resume_and_boot_apply(self):
        self.assertTrue(self.call('pause')['paused'])
        (self.fixture/'state.json').unlink()
        self.write(self.charger/'charge_type','Fast')
        self.assertTrue(self.call('apply')['stopped'])
        self.assertEqual((self.charger/'charge_type').read_text(),'N/A')
        self.assertFalse(self.call('resume')['stopped'])

    def test_charge_once_returns_to_limit_after_real_full(self):
        self.write(self.battery/'capacity',95)
        self.assertTrue(self.configure()['stopped'])
        self.assertFalse(self.call('full_once')['stopped'])
        self.write(self.battery/'capacity',100)
        self.write(self.charger/'status','Charging')
        self.assertTrue(self.call('apply')['full_once'])
        self.write(self.charger/'status','Full')
        full=self.call('apply')
        self.assertFalse(full['full_once']);self.assertTrue(full['stopped'])

    def test_disable_limit_releases_owned_pause(self):
        self.write(self.battery/'capacity',90)
        self.configure()
        result=self.call('configure',dict(enabled='0',start='70',stop='80'))
        self.assertFalse(result['stopped'])
        self.assertEqual((self.charger/'charge_type').read_text(),'Fast')

    def test_bad_input_does_not_change_config_or_hardware(self):
        initial=(self.config/'mu300-charge').read_bytes()
        for body in [dict(enabled='1',start='80',stop='80'),dict(enabled='1',start='1',stop='80'),
                     dict(enabled='1',start='70',stop='101'),dict(enabled='1;reboot',start='70',stop='80'),
                     dict(enabled=True,start='70',stop='80')]:
            self.assertFalse(self.call('configure',body)['ok'])
            self.assertEqual((self.config/'mu300-charge').read_bytes(),initial)
            self.assertEqual((self.charger/'charge_type').read_text().strip(),'Fast')

    def test_otg_source_keeps_pause_until_power_sink_returns(self):
        self.call('pause')
        self.write(self.charger/'usb_type','SDP [ACA]')
        result=self.call('resume')
        self.assertTrue(result['pending'])
        self.assertEqual((self.charger/'charge_type').read_text(),'N/A')
        self.write(self.charger/'usb_type','[SDP] ACA')
        self.assertFalse(self.call('apply')['stopped'])
        self.assertEqual((self.charger/'charge_type').read_text(),'Fast')

    def test_unavailable_battery_is_not_a_percentage(self):
        self.write(self.battery/'capacity','invalid')
        self.assertIsNone(self.call()['capacity'])
        self.assertEqual(self.call('pause')['error'],'charge_unavailable')

    def test_real_watch_receives_events_and_checks_soc_without_events(self):
        docker=['docker','exec',self.container]
        # The base image has not run procd, which normally creates /run.
        subprocess.run(docker+['/bin/sh','-c','mkdir -p /run /var/run/ubus; /sbin/ubusd >/tmp/charge-ubus.log 2>&1 &'],check=True)
        for attempt in range(30):
            if subprocess.run(docker+['ubus','list'],capture_output=True).returncode==0:break
            time.sleep(.1)
        else:self.fail('Fixture ubus did not start')
        self.write(self.battery/'capacity',90)
        self.configure()
        command=('echo $$ > /fixture/watch.pid; exec env MU300_CHARGE_CONFIG=/fixture/config '
                 'MU300_CHARGE_SYS=/fixture/power MU300_CHARGE_STATE=/fixture/state.json '
                 'MU300_CHARGE_TYPEC=/fixture/typec MU300_CHARGE_DEVICE=u30air '
                 '/usr/bin/ucode /usr/libexec/unisoc-modem/charge-watch.uc')
        watch_log=self.fixture/'watch.log'
        errors=watch_log.open('wb');self.addCleanup(errors.close)
        watcher=subprocess.Popen(docker+['/bin/sh','-c',command],stdout=subprocess.PIPE,stderr=errors)
        def wait_for(predicate,seconds):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if watcher.poll() is not None:
                    self.fail(watch_log.read_text())
                if predicate():return
                time.sleep(.1)
            self.fail('Charge policy did not react in time: '+watch_log.read_text())
        try:
            wait_for(lambda:(self.fixture/'watch.pid').exists(),3)
            self.write(self.battery/'capacity',70)
            # Under ARM emulation startup can exceed a fixed 300 ms sleep.
            # Retry fixture-only events until the listener is actually ready.
            def event_received():
                subprocess.run(docker+['ubus','send','mu300.charge','{}'],check=True)
                return (self.charger/'charge_type').read_text()=='Fast'
            wait_for(event_received,3)
            # Real FGU percentages do not generate regular change events.
            self.write(self.battery/'capacity',90)
            wait_for(lambda:(self.charger/'charge_type').read_text()=='N/A',33)
        finally:
            if (self.fixture/'watch.pid').exists():
                subprocess.run(docker+['/bin/busybox','kill','-TERM',(self.fixture/'watch.pid').read_text().strip()],check=False)
            watcher.communicate(timeout=5)
        self.assertEqual(watcher.returncode,0)


if __name__=='__main__':unittest.main()
