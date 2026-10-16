#!/usr/bin/env python3
"""Build a default OpenWrt archive without bundled VPN/proxy applications."""
import argparse
import io
import os
import re
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

APPS = {'xray', 'sing-box', 'singbox', 'hev-socks5-tunnel', 'openvpn', 'openconnect',
        'ocserv', 'tailscale', 'tailscaled', 'zerotier', 'zerotier-one', 'zerotier-cli',
        'zerotier-idtool', 'wireguard-go', 'wg', 'wg-quick', 'ipsec', 'charon',
        'strongswan', 'xl2tpd', 'pptpd', 'sstpc', 'softethervpn', 'mu300-vpn'}

def forbidden(name):
    parts=PurePosixPath(name).parts
    return any(p in APPS or p in {'vpn.conf','vpn.conf.example','mu300-vpn.service'}
               or re.fullmatch(r'[SK]\d+mu300-vpn',p) or p.startswith(('luci-app-openvpn','luci-app-wireguard')) for p in parts)

def toolkit(data):
    text=data.decode('utf-8')
    if 'vpn_enabled() {' not in text:
        if 'menu_vpn' in text or 'mu300-vpn' in text:raise ValueError('unrecognized toolkit VPN layout')
        return data
    start=text.index('vpn_enabled() {');end=text.index('# Live radio quality:',start)
    text=text[:start]+text[end:]
    text=text.replace('VPN_CONF=/etc/mu300/vpn.conf\n','')
    text=text.replace('"Wi-Fi (hotspot, or join a network)" "VPN"','"Wi-Fi (hotspot, or join a network)"')
    text=text.replace('            8) menu_vpn ;;\n            9) menu_ttl ;;','            8) menu_ttl ;;')
    text=text.replace(' mu300-vpn ', ' ').replace('Network, mobile data, VPN','Network, mobile data')
    if 'menu_vpn' in text or 'mu300-vpn' in text or 'VPN_CONF' in text:
        raise ValueError('toolkit still refers to removed VPN service')
    return text.encode('utf-8')

def strip(archive):
    archive=Path(archive)
    removed=[]
    fd,tmp=tempfile.mkstemp(prefix=archive.name+'.no-vpn.',dir=archive.parent)
    os.close(fd)
    try:
        with tarfile.open(archive,'r|gz') as src,tarfile.open(tmp,'w:gz',compresslevel=6) as dst:
            for member in src:
                name=member.name.removeprefix('./')
                if forbidden(name):
                    removed.append(name);continue
                if name.startswith('lib/apk/packages/') and any(PurePosixPath(name).name.startswith(app+'-') for app in APPS):
                    raise ValueError('VPN APK installed in base; remove it from package selection: '+name)
                data=src.extractfile(member) if member.isfile() else None
                if name=='opt/mu300/bin/mu300-toolkit':
                    content=toolkit(data.read());member.size=len(content);data=io.BytesIO(content)
                dst.addfile(member,data)
        os.chmod(tmp,archive.stat().st_mode & 0o777)
        os.replace(tmp,archive)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('No-VPN payload: removed '+str(len(removed))+' entries: '+', '.join(removed),flush=True)
    return removed

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path)
    strip(p.parse_args().archive)
