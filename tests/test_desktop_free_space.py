"""Partition-table and encrypted-data routing tests; no attached device writes."""
import importlib.util
from pathlib import Path
import struct
import unittest
import uuid
from unittest.mock import Mock, patch
import zlib

TOP=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('free_installer',TOP/'desktop/installer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def snapshot(sectors=64*2097152,parts=None):
    if parts is None:parts=[('userdata',2048,32*2097152-1)]
    table=bytearray(128*128)
    for i,(name,a,b) in enumerate(parts):
        table[i*128:i*128+16]=uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le
        table[i*128+16:i*128+32]=uuid.uuid4().bytes_le
        struct.pack_into('<QQ',table,i*128+32,a,b)
        encoded=name.encode('utf-16-le');table[i*128+56:i*128+56+len(encoded)]=encoded
    guid=uuid.uuid4().bytes_le
    def header(at,alt,tab):
        h=bytearray(512);h[:8]=b'EFI PART'
        struct.pack_into('<III',h,8,0x10000,92,0)
        struct.pack_into('<QQQQ',h,24,at,alt,34,sectors-34)
        h[56:72]=guid;struct.pack_into('<QIII',h,72,tab,128,128,zlib.crc32(table))
        struct.pack_into('<I',h,16,zlib.crc32(h[:92]));return bytes(h)
    return bytes(512)+header(1,sectors-1,2)+table, bytes(table)+header(sectors-1,1,sectors-33)

class FreeSpace(unittest.TestCase):
    def test_64gb_gap_is_used_without_changing_userdata_or_other_entries(self):
        total=64*2097152;first,last=snapshot(total)
        info=m.gpt_space(first,last,total);need=10*2097152
        offset=m.free_root_range(info,need)
        self.assertEqual(offset,32*2097152)
        a,b=m.gpt_add_root(first,last,total,offset,need)
        changed=m.gpt_space(a,b,total)
        self.assertEqual(changed['parts'][0],info['parts'][0])
        self.assertEqual(a[:512],first[:512])
        self.assertEqual(a[1024:1152],first[1024:1152])
        self.assertEqual(a[1280:],first[1280:])
        self.assertEqual(changed['parts'][1],{'n':2,'name':'mu300root','start':offset,'end':offset+need-1})

    def test_total_free_does_not_replace_a_contiguous_aligned_gap(self):
        total=16*2097152
        first,last=snapshot(total,[('userdata',2048,6*2097152-1),('reserved',10*2097152,12*2097152-1)])
        info=m.gpt_space(first,last,total)
        self.assertGreater(sum(n for _,n in info['gaps']),6*2097152)
        self.assertIsNone(m.free_root_range(info,6*2097152))
        info['safe_gaps']=[]
        self.assertIsNone(m.free_root_range(info,2*2097152))

    def test_corrupt_copies_overlap_and_metadata_encroachment_are_rejected(self):
        total=64*2097152;first,last=snapshot(total)
        bad=bytearray(last);bad[1]^=1
        with self.assertRaisesRegex(ValueError,'checksum/copy'):m.gpt_space(first,bad,total)
        a,b=snapshot(total,[('userdata',2048,10000),('other',9000,20000)])
        with self.assertRaisesRegex(ValueError,'Overlapping'):m.gpt_space(a,b,total)
        a,b=snapshot(total,[('userdata',1,10000)])
        with self.assertRaisesRegex(ValueError,'outside'):m.gpt_space(a,b,total)
        with self.assertRaises(ValueError):m.gpt_space(first,last,total-1)
        for off,size in ((2048,2*2097152),(32*2097152+1,2*2097152),(32*2097152,40*2097152)):
            with self.assertRaises(ValueError):m.gpt_add_root(first,last,total,off,size)

    def test_encrypted_android_with_free_gap_skips_reset_and_offline_shrink(self):
        a=Mock();a.model='V50';a.slot='a';a.linux='b';a.args=Mock()
        s={'NODE':'mmcblk0p1','START':2048,'SIZE':32*2097152-2048,'DISK_SIZE':64*2097152,
           'CID':'a'*32,'STATE':'encrypted','TYPE':'block','SOURCE':'/dev/block/dm-0','EXT':'','MAGIC':''}
        first,last=snapshot(s['DISK_SIZE']);space=m.gpt_space(first,last,s['DISK_SIZE'])
        space.update(first=first,last=last);a.storage.return_value=s;a.gpt.return_value=space
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            args=Mock(boot_openwrt=False,tf=False,resume=False,reinstall_part=False,data=False,
                      format_userdata=False,size='10',backup_dir=tmp)
            def backup(path,storage):
                path.mkdir();(path/'gpt-first.bin').write_bytes(first);(path/'gpt-last.bin').write_bytes(last)
            a.backup.side_effect=backup
            expected=m.Outcome('success','free root')
            with patch.object(m,'Android',return_value=a),patch.object(m,'module'),patch.object(m,'confirm'), \
                 patch.object(m,'encrypted',side_effect=AssertionError('encrypted shrink path')), \
                 patch.object(m,'free_write',return_value=expected) as write:
                self.assertIs(m.install(args,Path(tmp),{}),expected)
                self.assertEqual(write.call_args.args[-2:],(32*2097152,10*2097152))
                a.reboot.assert_not_called();a.flash.assert_not_called()

    def test_failed_image_verification_never_writes_boot_or_selects_a_slot(self):
        total=64*2097152;first,last=snapshot(total);space=m.gpt_space(first,last,total)
        space.update(first=first,last=last)
        a=Mock();a.args=Mock();a.t='/tmp/stage';a.shell.return_value='a'*64+'  image'
        a.run.side_effect=[None,RuntimeError('image readback failed')]
        with patch.object(m,'settings',return_value=''):
            with self.assertRaisesRegex(RuntimeError,'readback'):m.free_write(a,TOP,Mock(),{'kernel':'7.2'},
                {'NODE':'mmcblk0p1','CID':'a'*32,'DISK_SIZE':total},space,32*2097152,10*2097152)
        a.flash.assert_not_called();a.live.assert_not_called()

if __name__=='__main__':unittest.main()
