"""CLI backup uses verified downloads; no real ADB calls or device writes."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib

TOP=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('binary_cli_installer',TOP/'desktop/installer.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class CLIBinaryBackup(unittest.TestCase):
    def test_helper_is_generated_from_the_shared_backend(self):
        self.assertEqual((TOP/'desktop/binary_io.py').read_bytes(),(TOP/'installer/backend/binary_io.py').read_bytes())

    def test_full_backup_downloads_partition_files_without_reading_them_into_stdout(self):
        table=bytes(128*128);sectors=1000;front=34;tail=967
        def header(at,other,lba):
            raw=bytearray(512);raw[:8]=b'EFI PART';struct.pack_into('<II',raw,8,0x10000,92)
            struct.pack_into('<QQ',raw,24,at,other);struct.pack_into('<QQ',raw,40,34,966)
            struct.pack_into('<QIII',raw,72,lba,128,128,zlib.crc32(table))
            struct.pack_into('<I',raw,16,zlib.crc32(raw[:92]));return bytes(raw)
        primary=header(1,999,2);alternate=header(999,1,967)
        first=bytes(512)+primary+table;last=table+alternate
        android=object.__new__(installer.Android);android.serial='chosen';android.slot='a'
        storage={'NODE':'mmcblk0p30','DISK_SIZE':sectors}
        downloads=[]
        def download(command,destination,expected_size=None):
            name=Path(destination).name
            data=first if name=='gpt-first.bin' else last if name=='gpt-last.bin' else bytes(range(256))*(expected_size//256)
            self.assertEqual(len(data),expected_size)
            Path(destination).write_bytes(data);downloads.append((command,name,expected_size))
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(android,'read',side_effect=[primary,alternate]) as read, \
             patch.object(android,'download',side_effect=download), \
             patch.object(android,'shell',return_value='8192'):
            backup=Path(temp)/'backup';android.backup(backup,storage)
            self.assertEqual(read.call_count,2)
            self.assertEqual(len(downloads),15)
            self.assertEqual((backup/'boot_a.img').stat().st_size,8192)
            for line in (backup/'SHA256SUMS').read_text().splitlines():
                checksum,name=line.split()
                self.assertEqual(checksum,hashlib.sha256((backup/name).read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
