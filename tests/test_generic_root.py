"""Execute generic init storage selection with fake sysfs and regular files."""
from helpers import TOP, ShellTest

INIT=(TOP/'boot/init').read_text()


class GenericRoot(ShellTest):
    def setUp(self):
        super().setUp()
        self.dev=self.tmp/'dev';self.dev.mkdir()
        self.sys=self.tmp/'sys';self.run=self.tmp/'run';self.run.mkdir()
        self.etc=self.tmp/'etc';self.etc.mkdir()
        (self.etc/'mu300-internal-ext4.sh').write_bytes((TOP/'boot/internal-ext4.sh').read_bytes())
        (self.sys/'block/mmcblk0/device').mkdir(parents=True)
        (self.sys/'block/mmcblk0/device/type').write_text('MMC\n')
        self.part('mmcblk0p76','mu300root','mu300root')

    def part(self,name,partname,label):
        disk=name.split('p')[0]
        p=self.sys/'block'/disk/name;p.mkdir(parents=True,exist_ok=True)
        (p/'uevent').write_text('PARTNAME='+partname+'\n')
        raw=bytearray(4096);raw[1080:1082]=bytes.fromhex('53ef');raw[1144:1144+len(label)]=label.encode()
        (self.dev/name).write_bytes(raw)

    def local(self,text):
        return text.replace('/sys/',str(self.sys)+'/').replace('/dev/',str(self.dev)+'/').replace('/run/',str(self.run)+'/').replace('/etc/',str(self.etc)+'/').replace('[ -b ','[ -f ')

    def test_only_unique_internal_partition_with_exact_ext4_label_is_selected(self):
        start=INIT.index('find_gpt_root() {');function=self.local(INIT[start:INIT.index('\n}',start)+2])
        for shell in self.each_shell():
            for case,want in [('good',True),('prefix',False),('duplicate',False),('not-mmc',False)]:
                self.part('mmcblk0p76','mu300root','mu300rootX' if case=='prefix' else 'mu300root')
                self.part('mmcblk1p1','mu300root','mu300root')
                (self.sys/'block/mmcblk0/device/type').write_text('SD\n' if case=='not-mmc' else 'MMC\n')
                extra=self.sys/'block/mmcblk0/mmcblk0p77/uevent'
                extra.unlink(missing_ok=True)
                if case=='duplicate':self.part('mmcblk0p77','mu300root','mu300root')
                r=self.sh(shell,function+'\nfind_gpt_root')
                self.assertEqual(r.returncode,0 if want else 1,r.stderr)
                self.assertEqual(r.stdout.strip(),str(self.dev/'mmcblk0p76') if want else '')

    def test_explicit_desktop_partition_overrides_old_tf_marker(self):
        start=INIT.index('# A TF-only image must never fall through')
        end=INIT.index('# busybox mount only',start)
        code=self.local(INIT[start:end]).replace('/disk',str(self.tmp/'disk')).replace('/newroot',str(self.tmp/'newroot'))
        card=self.dev/'mmcblk1p1';card.write_bytes(bytearray(4096))
        p=self.sys/'class/block/mmcblk1p1';p.mkdir(parents=True);(p/'size').write_text('8192\n')
        prefix='''log(){ :; }
sleep(){ echo sleep >> "$STUBLOG/events"; }
mdev(){ :; }
setup_usb_gadget(){ :; }
read_usb_boot_policy(){ :; }
find_root_offset(){ echo region >> "$STUBLOG/events"; [ "$REGION" = 1 ] && { echo 4096; return 0; }; return 1; }
find_gpt_root(){ echo part >> "$STUBLOG/events"; [ "$PART" = 1 ] && { echo "$GPPATH"; return 0; }; return 1; }
mount(){ [ "$MOUNT_FAIL" != 1 ]; }
ROOT_OFFSET=4096
'''
        cases=[('part','sd',1,1,0,True),('part','sd',1,1,1,False),('part','sd',1,0,0,False),
               ('','sd',1,1,0,False),('','',0,1,0,True),('','',1,1,0,False)]
        for shell in self.each_shell():
            for mode,target,region,part,fail,mounted in cases:
                (self.etc/'mu300-desktop-root-mode').write_text(mode+'\n');(self.etc/'mu300-root-target').write_text(target+'\n')
                events=self.tmp/'events';events.unlink(missing_ok=True)
                r=self.sh(shell,prefix+code+'\necho "result=$root_mounted internal=$internal_root"',
                          REGION=region,PART=part,MOUNT_FAIL=fail,GPPATH=self.dev/'mmcblk0p76')
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn('result='+str(int(mounted)),r.stdout)
                calls=events.read_text().splitlines() if events.exists() else []
                if mode=='part':
                    self.assertEqual(calls,['part'])
                    self.assertIn('internal=',r.stdout)
                elif target=='sd':self.assertEqual(calls,[])
                elif region:self.assertEqual(calls,['region'])
            raw=bytearray(4096);raw[1080:1082]=bytes.fromhex('53ef');raw[1144:1152]=b'mu300sd\0';card.write_bytes(raw)
            (self.etc/'mu300-desktop-root-mode').write_text('');(self.etc/'mu300-root-target').write_text('')
            events.unlink(missing_ok=True)
            r=self.sh(shell,prefix+code+'\necho "result=$root_mounted"',REGION=1,PART=1,MOUNT_FAIL=0,GPPATH=self.dev/'mmcblk0p76')
            self.assertEqual(r.returncode,0,r.stderr);self.assertIn('result=1',r.stdout)
            self.assertFalse(events.exists(),'valid TF must win without probing internal roots')
            card.write_bytes(bytearray(4096))
