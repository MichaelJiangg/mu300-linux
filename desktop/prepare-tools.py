#!/usr/bin/env python3
"""Build the desktop-only ARM64 maintenance bundle; never install it into Magisk's rootfs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

FILES=('sbin/fsck.f2fs','sbin/resize.f2fs','lib/ld-musl-aarch64.so.1','lib/libf2fs.so.10',
 'lib/libuuid.so.1','lib/libgcc_s.so.1','usr/bin/ucode','lib/libucode.so.20230711',
 'lib/libjson-c.so.5','usr/lib/ucode/fs.so','usr/sbin/resize2fs','usr/sbin/e2fsck',
 'lib/libe2p.so.2','lib/libext2fs.so.2','lib/libcom_err.so.0','lib/libblkid.so.1')

def prepare(source,out):
    hashes={}
    for name in FILES:
        choices=[source/name,source/'usr'/name]
        if name=='sbin/resize.f2fs':choices.append(source/'sbin/fsck.f2fs')
        found=next((p for p in choices if p.is_file()),None)
        if found is None:raise ValueError('missing ARM64 maintenance file: '+name)
        data=found.read_bytes()
        if data[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',data,18)[0]!=183:raise ValueError('not ARM64 ELF: '+name)
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(0o755)
        hashes[name]=hashlib.sha256(data).hexdigest()
    (out/'manifest.json').write_text(json.dumps({'sha256':hashes},indent=2)+'\n')
    return hashes

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();prepare(a.root,a.out)
