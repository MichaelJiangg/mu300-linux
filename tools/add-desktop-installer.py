#!/usr/bin/env python3
"""Augment a Magisk ZIP without rebuilding/changing its original runtime files."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

TOP=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desktop_package',TOP/'desktop/package.py')
pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)

def augment(source,out,tools,kernel,exe=None):
    if source.resolve()==out.resolve():raise ValueError('input and output must differ')
    if out.exists():raise ValueError('output exists; do not overwrite a release')
    with tempfile.TemporaryDirectory(prefix='mu300-desktop-') as temp:
        stage=Path(temp)
        with zipfile.ZipFile(source) as old:
            if len(set(old.namelist()))!=len(old.namelist()):raise ValueError('duplicate ZIP entries')
            original={}
            for info in old.infolist():
                name=PurePosixPath(info.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename:
                    raise ValueError('unsafe ZIP entry: '+info.filename)
                if info.is_dir():continue
                data=old.read(info);p=stage/info.filename;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                original[info.filename]=info
        manifest=pkg.assemble(stage,tools,kernel,exe)
        manifest['origin']={'archive':source.name,'sha256':pkg.sha(source),'runtime':'unchanged original archive'}
        (stage/'desktop/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        out.parent.mkdir(parents=True,exist_ok=True)
        partial=out.with_suffix('.partial')
        with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    n=p.relative_to(stage).as_posix()
                    original_name=next((old for old,new in manifest['magisk_layout'].items() if new==n),None)
                    if original_name in original:
                        info=copy.copy(original[original_name]);info.filename=n;info.orig_filename=n
                        z.writestr(info,p.read_bytes())
                    else:z.write(p,n)
        with zipfile.ZipFile(partial) as z:
            if z.testzip():raise ValueError('ZIP CRC verification failed')
            import hashlib
            for n,want in manifest['magisk'].items():
                if hashlib.sha256(z.read(n)).hexdigest()!=want:raise ValueError('original Magisk member changed: '+n)
        partial.replace(out)
        print(out)
        print('Original Magisk members verified:',len(manifest['magisk']))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--tools',type=Path,required=True);p.add_argument('--kernel',choices=('6.18','7.2'),required=True);p.add_argument('--exe',type=Path)
    a=p.parse_args();augment(a.source,a.out,a.tools,a.kernel,a.exe)
