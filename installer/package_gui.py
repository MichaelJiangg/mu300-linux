"""Attach a fingerprinted portable desktop build to an existing package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def sources():
    paths = [HERE/n for n in ('backend_entry.py','build.py','package_gui.py','platform-tools.json','platform-tools-macos.json','GUIDE.md')]
    paths += list((HERE/'backend').glob('*.py'))
    paths += [p for p in (HERE/'ui/src').rglob('*') if p.is_file()]
    paths += [HERE/'ui'/n for n in ('package.json','package-lock.json','vite.config.ts','tailwind.config.js','postcss.config.js','tsconfig.json','index.html','rust-toolchain.toml')]
    paths += [HERE/'ui/src-tauri'/n for n in ('Cargo.toml','Cargo.lock','build.rs','tauri.conf.json','src/main.rs','capabilities/default.json','icons/icon.ico','icons/icon.icns','icons/icon.png')]
    # Git checkouts can normalize CRLF on the native macOS build runner.
    # Only source text is normalized; binary artifact hashes stay exact.
    text = {'.py','.ts','.tsx','.json','.toml','.rs','.js','.html','.md','.css','.lock'}
    return {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            if p.suffix in text else digest(p) for p in sorted(paths)}


def attach(package, artifact=None, required=True):
    package = Path(package)
    artifact = Path(artifact or os.environ.get('OPENWRT_GUI_ARTIFACT', HERE/'artifacts/windows'))
    metadata = artifact/'build.json'
    if not metadata.is_file():
        if required:
            raise ValueError('Portable GUI build missing; run python installer/build.py or set OPENWRT_GUI_ARTIFACT')
        return False
    build = json.loads(metadata.read_text())
    if build['source'] != sources():
        raise ValueError('Portable GUI build is stale; rebuild installer/build.py')
    for name, wanted in build['files'].items():
        path = (artifact/name).resolve()
        if not path.is_relative_to(artifact.resolve()) or digest(path) != wanted:
            raise ValueError('Portable build checksum mismatch: '+name)
    shutil.copy2(artifact/'OpenWrt-Installer.exe', package/'OpenWrt-Installer.exe')
    shutil.copytree(artifact/'tools', package/'tools', dirs_exist_ok=True)
    mac_artifact = os.environ.get('OPENWRT_GUI_MACOS_ARTIFACT')
    if mac_artifact:
        mac_artifact = Path(mac_artifact)
        mac_metadata = mac_artifact/'build.json'
        mac_build = json.loads(mac_metadata.read_text())
        if mac_build.get('platform') != 'macos-arm64' or mac_build['source'] != sources():
            raise ValueError('Apple Silicon GUI build is stale or has the wrong architecture')
        for name, wanted in mac_build['files'].items():
            path = (mac_artifact/name).resolve()
            if not path.is_relative_to(mac_artifact.resolve()) or digest(path) != wanted:
                raise ValueError('Apple Silicon build checksum mismatch: '+name)
        # Flatten framework links for ZIP extractors without symlink privileges.
        shutil.copytree(mac_artifact/'OpenWrt-Installer.app', package/'OpenWrt-Installer.app', dirs_exist_ok=True)
        shutil.copytree(mac_artifact/'tools', package/'tools', dirs_exist_ok=True)
        (package/'docs').mkdir(exist_ok=True)
        shutil.copy2(mac_metadata, package/'docs/GUI-BUILD-macos.json')
    docs = package/'docs'
    docs.mkdir(exist_ok=True)
    shutil.copy2(HERE/'GUIDE.md', docs/'GUI-GUIDE.md')
    shutil.copy2(HERE/'PROTOCOL.md', docs/'INSTALLER-PROTOCOL.md')
    shutil.copy2(HERE/'README.md', docs/'GUI-BUILD.md')
    shutil.copy2(HERE/'VERIFICATION.md', docs/'GUI-VERIFICATION.md')
    if (HERE/'screenshots').is_dir():
        shutil.copytree(HERE/'screenshots', docs/'screenshots', dirs_exist_ok=True)
    (package/'START-HERE.md').write_text((HERE/'GUIDE.md').read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
    shutil.copy2(metadata, docs/'GUI-BUILD.json')
    return True


def size_report(package, archive=None):
    package = Path(package)
    gui = package/'OpenWrt-Installer.exe'
    tools = sum(p.stat().st_size for name in ('tools','scripts','desktop') for p in (package/name).rglob('*') if p.is_file())
    payload_roots = [package/'payload'] if (package/'payload').is_dir() else [package/'files']
    payload = sum(p.stat().st_size for root in payload_roots for p in root.rglob('*') if p.is_file())
    return {'gui_bytes':gui.stat().st_size if gui.is_file() else 0, 'backend_and_tools_bytes':tools,
            'firmware_payload_bytes':payload, 'archive_bytes':Path(archive).stat().st_size if archive else None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--archive', type=Path)
    a = parser.parse_args()
    attach(a.package,a.artifact)
    print(json.dumps(size_report(a.package,a.archive),indent=2))
