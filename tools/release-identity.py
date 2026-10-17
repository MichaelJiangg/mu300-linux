#!/usr/bin/env python3
"""One private release identity for the image, installer and archive filename."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def identify(repo,profile,kernel,openwrt='25.12.5',epoch=None,version=None):
    repo=Path(repo).resolve()
    git_options=['git','-c','safe.directory='+str(repo),'-C',str(repo)]
    marker=repo/'.git'
    if os.name!='nt' and marker.is_file():
        value=marker.read_text().strip().removeprefix('gitdir:').strip()
        if re.match(r'^[A-Za-z]:[/\\]',value):
            directory='/mnt/'+value[0].lower()+'/'+value[3:].replace('\\','/')
            git_options+=['--git-dir='+directory,'--work-tree='+str(repo)]
    def git(*args):
        result=subprocess.run([*git_options,*args],capture_output=True)
        if result.returncode:
            raise ValueError('Cannot read release Git state: '+result.stderr.decode('utf-8','replace').strip())
        return result.stdout
    commit=git('rev-parse','HEAD').decode().strip()
    fingerprint=hashlib.sha256(git('rev-parse','HEAD^{tree}')+git('diff','--binary','HEAD'))
    untracked=git('ls-files','--others','--exclude-standard','-z').split(b'\0')
    dirty=bool(git('status','--porcelain','--untracked-files=normal').strip())
    for raw in sorted(filter(None,untracked)):
        path=repo/raw.decode('utf-8')
        if path.is_file():
            fingerprint.update(raw+b'\0')
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1 << 20),b''):fingerprint.update(chunk)
    epoch=int(time.time() if epoch is None else epoch)
    stamp=datetime.fromtimestamp(epoch,timezone.utc)
    source=fingerprint.hexdigest()
    private=version or f'r{stamp:%Y%m%d.%H%M%S}-g{commit[:8]}-s{source[:8]}'
    for label,value in (('profile',profile),('kernel',kernel),('version',private),('OpenWrt',openwrt)):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+\-]{0,150}',value):
            raise ValueError('Invalid release '+label)
    kernel_label=re.match(r'\d+(?:\.\d+){1,2}',kernel)
    kernel_label=kernel_label[0] if kernel_label else kernel
    return {'format':1,'private_version':private,'image_version':profile+'-'+private,
            'package_name':f'{profile}-openwrt-{openwrt}-{private}-k{kernel_label}',
            'profile':profile,'openwrt':openwrt,'kernel_release':kernel,
            'source_commit':commit,'source_fingerprint':source,'source_dirty':dirty,
            'build_epoch':epoch,'build_time_utc':stamp.isoformat(timespec='seconds')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--profile',required=True);parser.add_argument('--kernel',required=True)
    parser.add_argument('--openwrt',default='25.12.5');parser.add_argument('--epoch',type=int)
    parser.add_argument('--version');parser.add_argument('--output',type=Path)
    parser.add_argument('--field',choices=('private_version','image_version','package_name'))
    args=parser.parse_args()
    info=identify(args.repo,args.profile,args.kernel,args.openwrt,args.epoch,args.version)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(info[args.field] if args.field else json.dumps(info,indent=2))


if __name__=='__main__':main()
