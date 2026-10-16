#!/usr/bin/env python3
"""Verify a hybrid ZIP and exercise its desktop boot builder without hardware."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

def verify(path):
    with tempfile.TemporaryDirectory(prefix='mu300 desktop ') as temp:
        stage=Path(temp)
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                p=PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:raise ValueError('unsafe archive path')
            if archive.testzip():raise ValueError('ZIP CRC failure')
            manifest=json.loads(archive.read('desktop/manifest.json'))
            for group in ('magisk','desktop'):
                for name,want in manifest[group].items():
                    if hashlib.sha256(archive.read(name)).hexdigest()!=want:raise ValueError('checksum failure: '+name)
            archive.extractall(stage)
        print('ZIP checksums passed:',path,flush=True)
        shared=manifest.get('magisk_layout',{}).get('mu300-openwrt.tar.gz','mu300-openwrt.tar.gz')
        if shared not in manifest['magisk'] or 'desktop/files/rootfs.tar.gz' in manifest['desktop']:
            raise ValueError('expected one shared rootfs archive')
        if manifest.get('format')==2:
            allowed={'OpenWrt-Installer.exe','OpenWrt-Installer.py','START-HERE.md','module.prop','customize.sh'}
            if {p.name for p in stage.iterdir() if p.is_file()}-allowed:
                raise ValueError('unexpected top-level file')
            if not (stage/'START-HERE.md').is_file():
                raise ValueError('missing root user guide START-HERE.md')
        subprocess.run([sys.executable,str(stage/'OpenWrt-Installer.py'),'--check-boot'],check=True)
        subprocess.run([sys.executable,str(stage/'OpenWrt-Installer.py'),'--check-rootfs'],check=True)
        if sys.platform=='win32' and (stage/'OpenWrt-Installer.exe').exists():
            subprocess.run([str(stage/'OpenWrt-Installer.exe'),'--check-boot'],check=True)
            subprocess.run([str(stage/'OpenWrt-Installer.exe'),'--check-rootfs'],check=True)
            # Exercise a real CMD launcher from a path containing spaces.
            launcher=stage/('launchers/start-installer.cmd' if manifest.get('format')==2 else 'start-installer.cmd')
            subprocess.run(['cmd.exe','/c',str(launcher),'--check'],cwd=stage,input='\n',text=True,check=True)
        return {'archive':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'original_members':len(manifest['magisk']),'kernel':manifest['kernel'],'device_writes':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packages',type=Path,nargs='+');p.add_argument('--report',type=Path)
    a=p.parse_args();report=[verify(path) for path in a.packages]
    if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
