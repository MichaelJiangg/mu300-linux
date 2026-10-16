"""Behavior regressions for the six reviewed upstream fixes; no real device I/O."""
import gzip
import io
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tarfile
import unittest

TOP = Path(__file__).resolve().parents[1]
E5 = (TOP / 'devices/common/eic.py').exists()


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace('-', '_'), path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class UpstreamRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    @unittest.skipUnless(shutil.which('bash'), 'needs POSIX shell')
    def test_import_permissions_and_symlink_targets(self):
        helper = TOP / ('rootfs/overlay/opt/e5/android-import-perms.sh' if E5 else
                        'rootfs/overlay/opt/mu300/lib/android-import-perms.sh')
        props = 'dev/__properties__' if E5 else 'dev-properties'
        root = self.root / 'android'
        for name in ['vendor/bin/modem_control', 'vendor/etc/modem.xml', props+'/property_info', 'linkerconfig/ld.config.txt']:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture');p.chmod(0o700)
        for p in root.rglob('*'):
            if p.is_dir():p.chmod(0o700)
        outside=self.root/'outside';outside.write_text('keep');outside.chmod(0o600)
        (root/'vendor/alias').symlink_to(outside)
        owner=f'{os.getuid()}:{os.getgid()}'
        for shell in ['dash','bash','busybox']:
            if not shutil.which(shell):continue
            argv=[shell]+(['sh'] if shell=='busybox' else [])
            code='. "$1"; android_import_perms "$2" "$3" "$4"'
            r=subprocess.run(argv+['-c',code,'test',str(helper),str(root),props,owner],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((root/'vendor/bin/modem_control').stat().st_mode & 0o777,0o755)
            self.assertEqual((root/'vendor/etc/modem.xml').stat().st_mode & 0o777,0o644)
            self.assertEqual((root/props/'property_info').stat().st_mode & 0o777,0o444)
            self.assertEqual(outside.stat().st_mode & 0o777,0o600)
            # Healthy boots do no ownership/mode writes.
            r=subprocess.run(argv+['-c',code.replace('; android_import', '; chmod() { exit 91; }; chown() { exit 92; }; android_import'),
                                   'test',str(helper),str(root),props,owner],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

    def test_embedded_config_and_full_inventory(self):
        audit=module(TOP/'upstream/audit-bundle.py')
        (self.root/'modules').mkdir()
        cfg='CONFIG_KVM=y\nCONFIG_VIRTIO_NET=m\n'
        (self.root/'config').write_text(cfg)
        (self.root/'Image').write_bytes(b'ImageIKCFG_ST'+gzip.compress(cfg.encode())+b'IKCFG_ED')
        (self.root/'modules.in-tree').write_text('virtio_net.ko\n')
        (self.root/'modules/virtio_net.ko').write_bytes(b'module')
        audit.audit(self.root,'config')
        (self.root/'config').write_text(cfg.replace('KVM=y','KVM=n'))
        with self.assertRaisesRegex(ValueError,'embedded configuration'):audit.audit(self.root,'config')
        (self.root/'config').write_text(cfg)
        (self.root/'modules/virtio_net.ko').unlink()
        with self.assertRaisesRegex(ValueError,'Missing in-tree'):audit.audit(self.root,'config')
        (self.root/'modules.in-tree').write_text('../outside.ko\n')
        with self.assertRaisesRegex(ValueError,'Invalid module'):audit.audit(self.root,'config')
        (self.root/'Image').write_bytes(b'no config')
        with self.assertRaisesRegex(ValueError,'no embedded'):audit.audit(self.root,'config')

    def test_vendor_archive_modes_ignore_host_filesystem(self):
        if E5:self.skipTest('E5 packages imported files on Android itself')
        overlay=module(TOP/'tools/vendor-overlay.py')
        src=self.root/'subset';src.mkdir()
        for name in ['vendor/bin/modem_control','vendor/etc/modem.xml','dev-properties/property_info']:
            p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'data');p.chmod(0o700)
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w') as tar:overlay.add_tree(tar,src,'opt/mu300/android',set())
        data.seek(0)
        with tarfile.open(fileobj=data) as tar:
            modes={m.name:m.mode for m in tar}
            self.assertEqual(modes['opt/mu300/android/vendor/bin/modem_control'],0o755)
            self.assertEqual(modes['opt/mu300/android/vendor/etc/modem.xml'],0o644)
            self.assertEqual(modes['opt/mu300/android/dev-properties/property_info'],0o444)

    @unittest.skipUnless(shutil.which('cc'), 'needs host C compiler')
    def test_e5_factory_virtual_sensor_adapter(self):
        if not E5:self.skipTest('MU300 has a separate virtual sensor module')
        adapter=module(TOP/'devices/common/thermal.py')
        # Pinned E5 factory callback shape, including its last-returned error.
        original='''static int virtual_thm_get_temp(struct thermal_zone_device *tzd, int *temp)
{
 void *devdata = thermal_zone_device_priv(tzd);
 int i, ret = 0, max_temp = INT_MIN;
 struct thermal_zone_device *tz;
 struct real_tz_list *tz_list;
 struct virtual_thm_data *thm_data = devdata;
 struct device *dev = thm_data->vir_thm->dev;
 for (i = 0; i < thm_data->nr_thm; i++) {
  tz_list = &thm_data->tz_list[i]; tz = tz_list->tz_dev;
\t\tif (!tz || IS_ERR(tz))
\t\t\treturn -EINVAL;
  ret = thermal_zone_get_temp(tz, &tz_list->temp);
  if (ret) {
\t\t\tdev_err(dev, "fail to get temp\\n");
\t\t\treturn ret;
  }
  max_temp = max(max_temp, tz_list->temp);
 }
\t*temp = max_temp;
\treturn ret;
}
static void virtual_thm_unregister(void) {}
'''
        adapted=adapter.adapt(original)
        self.assertEqual(adapter.adapt(adapted),adapted)
        callback=adapted[:adapted.index('\nstatic void')]
        prelude='''#include <limits.h>
#include <errno.h>
struct device {int dummy;};
struct thermal_zone_device {void *priv; int value,err;};
struct real_tz_list {struct thermal_zone_device *tz_dev;int temp;};
struct virtual_thm {struct device *dev;};
struct virtual_thm_data {int nr_thm;struct real_tz_list *tz_list;struct virtual_thm *vir_thm;};
#define thermal_zone_device_priv(tz) ((tz)->priv)
#define IS_ERR(tz) ((tz)==(void*)-1)
#define max(a,b) ((a)>(b)?(a):(b))
#define dev_err_ratelimited(dev,fmt) ((void)(dev))
int thermal_zone_get_temp(struct thermal_zone_device *s,int *v){*v=s->value;return s->err;}
'''
        test='''int main(void){
 struct thermal_zone_device a={0,94000,0},b={0,0,-5};
 struct real_tz_list list[2]={{&a,0},{&b,0}};struct virtual_thm v={0};
 struct virtual_thm_data d={2,list,&v};struct thermal_zone_device z={&d,0,0};int t=0;
 if(virtual_thm_get_temp(&z,&t)||t!=94000)return 1;
 a.err=-5;t=123;if(virtual_thm_get_temp(&z,&t)!=-EIO||t!=123)return 2;
 return 0;}
'''
        c=self.root/'factory.c';c.write_text(prelude+callback+test)
        binary=self.root/'factory'
        subprocess.run(['cc','-Wall','-Werror',str(c),'-o',str(binary)],check=True,capture_output=True)
        subprocess.run([str(binary)],check=True)

    @unittest.skipUnless(shutil.which('bash') and shutil.which('flock'), 'needs Linux process locks')
    def test_keepalive_children_do_not_retain_upgrade_lock(self):
        if E5:self.skipTest('E5 updater has no self-update keepalive path')
        src=(TOP/'rootfs/overlay/opt/mu300/bin/mu300-update').read_text()
        code=src[src.index('keepalive_start() {'):src.index('\napply() {')]
        stubs=self.root/'bin';stubs.mkdir();mark=self.root/'ping-calls'
        ping=stubs/'ping'
        ping.write_text('#!/bin/sh\nif [ -e /proc/$$/fd/9 ]; then echo leaked >> "$MARK"; fi\necho probe >> "$MARK"\n')
        ping.chmod(0o755)
        env=dict(os.environ,PATH=str(stubs)+os.pathsep+os.environ['PATH'],MARK=str(mark),LOCKFILE=str(self.root/'lock'))
        for shell in ['dash','bash']:
            if not shutil.which(shell):continue
            mark.unlink(missing_ok=True)
            commands=code+'\nhave() { command -v "$1" >/dev/null; }; exec 9>>"$LOCKFILE"; flock 9; keepalive_start; sleep .2; keepalive_stop; exec 9>&-; exec 8>>"$LOCKFILE"; flock -n 8 || exit 93'
            r=subprocess.run([shell,'-c',commands],env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('probe',mark.read_text())
            self.assertNotIn('leaked',mark.read_text())

    @unittest.skipUnless(shutil.which('cc'), 'needs host C compiler')
    def test_virtual_sensor_partial_failure_and_all_failed(self):
        path=TOP/('devices/m8/sprd_virtual_thermal.c' if E5 else 'upstream/modules/mu300_thermal/mu300_thermal.c')
        source=path.read_text();name='sprd' if E5 else 'mu300'
        start=source.index(f'static int {name}_virtual_temp(')
        body=source[start:source.index('\nstatic const',start)]
        # Execute the production callback against deterministic sensor replies.
        harness='''#include <limits.h>
#include <errno.h>
struct thermal_zone_device {void *priv; int value,err;};
#define thermal_zone_device_priv(tz) ((tz)->priv)
#define max(a,b) ((a)>(b)?(a):(b))
int thermal_zone_get_temp(struct thermal_zone_device *s,int *v){*v=s->value;return s->err;}
'''+f'struct {name}_virtual {{unsigned count;struct thermal_zone_device *sensor[3];}};\n'+body+f'''
int main(void){{
 struct thermal_zone_device a={{0,94000,0}},b={{0,0,-5}},c={{0,89000,0}};
 struct {name}_virtual v={{3,{{&a,&b,&c}}}};
 struct thermal_zone_device zone={{&v,0,0}};int value=123;
 if({name}_virtual_temp(&zone,&value)||value!=94000)return 1;
 a.err=c.err=-5;value=123;
 if({name}_virtual_temp(&zone,&value)!=-EIO||value!=123)return 2;
 return 0;
}}
'''
        p=self.root/'sensor.c';p.write_text(harness);binary=self.root/'sensor'
        subprocess.run(['cc','-Wall','-Werror',str(p),'-o',str(binary)],check=True,capture_output=True)
        subprocess.run([str(binary)],check=True)

    @unittest.skipUnless(shutil.which('bash'), 'needs POSIX shell')
    def test_thermal_fallback_on_unreadable_or_stale_zone(self):
        if E5:self.skipTest('E5 uses its kernel thermal governors, no thermal-guard')
        source=(TOP/'rootfs/overlay/opt/mu300/bin/thermal-guard').read_text()
        code=source[source.index('native_cpu_cooling() {'):source.index('\nhottest() {')]
        root=self.root;zone=root/'sys/class/thermal/thermal_zone0'
        zone.mkdir(parents=True);(root/'sys/module/mu300_thermal').mkdir(parents=True)
        for name,value in [('type','soc-thmzone'),('mode','enabled'),('temp','94000'),('trip_point_0_type','passive'),('trip_point_0_temp','85000')]:
            (zone/name).write_text(value+'\n')
        dev=zone.parent/'cooling_device0';dev.mkdir();(dev/'type').write_text('cpufreq-cpu0\n');(zone/'cdev0').symlink_to(dev)
        def run():return subprocess.run(['bash','-c',code+'\nnative_cpu_cooling 95000'],env=dict(os.environ,R=str(root),HOT='85000'),capture_output=True).returncode
        self.assertEqual(run(),0)
        for bad in ['', '0','broken','70000']:
            (zone/'temp').write_text(bad+'\n');self.assertNotEqual(run(),0)
        (zone/'temp').write_text('94000\n');(zone/'trip_point_0_temp').write_text('100000\n');self.assertNotEqual(run(),0)

    def test_eic_adapter_idempotence_and_supported_limit(self):
        if not E5:self.skipTest('MU300 uses the tested upstream GPIO patch')
        adapter=module(TOP/'devices/common/eic.py')
        path=self.root/'drivers/gpio/gpio-eic-sprd.c';path.parent.mkdir(parents=True)
        path.write_text('#define SPRD_EIC_MAX_BANK\t3\n')
        adapter.apply(self.root);adapter.apply(self.root)
        self.assertIn('\t8',path.read_text())
        path.write_text('#define SPRD_EIC_MAX_BANK\t4\n')
        with self.assertRaises(ValueError):adapter.apply(self.root)


if __name__=='__main__':unittest.main()
