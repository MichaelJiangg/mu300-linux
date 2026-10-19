"""Exercise the real rpcd HTTP/UCI session boundary in a disposable OpenWrt container.

Requires the existing mu300-openwrt-base:25.12.5 image; never downloads an image,
exposes a host port, contacts a device or modifies the host UCI configuration.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time

TOP = Path(__file__).resolve().parents[2 if Path(__file__).parent.parent.name == 'openwrt' else 1]


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=30, **kwargs)


def check(repo, image):
    app = next(p for p in (repo/'openwrt/luci-app-t551m', repo/'openwrt/luci-app-mu300') if p.is_dir())
    acl = json.loads((app/'root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())
    old = copy.deepcopy(acl)
    old['luci-app-mu300']['write']['ubus'].pop('uci', None)
    with tempfile.TemporaryDirectory(prefix='auto-mode-acl-') as directory:
        fixture = Path(directory)
        for name, content in [('old', old), ('fixed', acl)]:
            (fixture/f'{name}.json').write_text(json.dumps(content))
        startup = """set -eu
mkdir -p /var/run/ubus /tmp/.uci
printf "config core 'main'\n option auto_work_mode '134'\n option at_port '/dev/fixture'\n" > /etc/config/unisoc_modem
printf "config core 'main'\n option marker 'unchanged'\n" > /etc/config/private_fixture
cat > /etc/config/rpcd <<'CONFIG'
config rpcd
 option socket '/var/run/ubus/ubus.sock'
config login
 option username 'root'
 option password '$6$Os1iACkvDWoDLwJz$uf32/I6y1SM4NbpK1GIuPt.epBDcIuxBP/tHhj7T9Ab34WVkzXIRW1p95tZzvnQLtJOO2/SJrztfW7y3XPTyG1'
 list read 'luci-base'
 list read 'luci-app-mu300'
 list write 'luci-base'
 list write 'luci-app-mu300'
CONFIG
cp /fixture/old.json /usr/share/rpcd/acl.d/luci-app-mu300.json
ubusd >/tmp/ubusd.log 2>&1 &
while [ ! -S /var/run/ubus/ubus.sock ]; do sleep 1; done
/sbin/rpcd -s /var/run/ubus/ubus.sock >/tmp/rpcd.log 2>&1 &
/usr/sbin/uhttpd -f -p 127.0.0.1:18080 -u /ubus -h /www >/tmp/http.log 2>&1 &
exec sleep 300
"""
        container = run('docker', 'run', '-d', '--pull=never', '--platform=linux/arm64', '--network=none',
                        '--mount', f'type=bind,src={fixture},dst=/fixture,readonly',
                        '--entrypoint', '/bin/sh', image, '-c', startup).strip()
        def rpc(session, obj, method, values):
            body = json.dumps(dict(jsonrpc='2.0', id=1, method='call', params=[session, obj, method, values]))
            reply = json.loads(run('docker', 'exec', container, 'uclient-fetch', '-q', '-O', '-',
                                 '--header=Content-Type: application/json', '--post-data='+body,
                                 'http://127.0.0.1:18080/ubus'))
            return reply if 'error' in reply else reply['result']
        def denied(reply):
            return reply == [6] or (isinstance(reply, dict) and reply.get('error', {}).get('code') == -32002)
        def login():
            reply = rpc('0'*32, 'session', 'login', dict(username='root', password='acl-fixture'))
            if not isinstance(reply, list) or reply[0] != 0 or len(reply) < 2:
                raise ValueError('fixture login: '+repr(reply))
            return reply[1]['ubus_rpc_session']
        try:
            for attempt in range(30):
                try:
                    sid = login()
                    break
                except (subprocess.SubprocessError, ValueError, KeyError, IndexError):
                    if attempt == 29:
                        raise
                    time.sleep(.1)
            # Old ACL allows a staged set, but HTTP rejects the commit before UCI runs.
            assert rpc(sid, 'uci', 'set', dict(config='unisoc_modem', section='main', values=dict(auto_work_mode='152')))[0] == 0
            old_commit = rpc(sid, 'uci', 'commit', dict(config='unisoc_modem'))
            assert denied(old_commit), old_commit
            assert run('docker', 'exec', container, 'uci', '-q', 'get', 'unisoc_modem.main.auto_work_mode').strip() == '134'
            # Login again after installing the real fixed ACL, as users do after an ACL update.
            run('docker', 'exec', container, 'cp', '/fixture/fixed.json', '/usr/share/rpcd/acl.d/luci-app-mu300.json')
            sid = login()
            for value in ('152', '134', 'default', 'default'):
                assert rpc(sid, 'uci', 'set', dict(config='unisoc_modem', section='main', values=dict(auto_work_mode=value)))[0] == 0
                assert rpc(sid, 'uci', 'commit', dict(config='unisoc_modem'))[0] == 0
                assert run('docker', 'exec', container, 'uci', '-q', 'get', 'unisoc_modem.main.auto_work_mode').strip() == value
                assert rpc(login(), 'uci', 'get', dict(config='unisoc_modem', section='main'))[1]['values']['auto_work_mode'] == value
            assert run('docker', 'exec', container, 'uci', '-q', 'get', 'unisoc_modem.main.at_port').strip() == '/dev/fixture'
            # The method grant does not override per-config UCI permissions.
            assert rpc(sid, 'uci', 'set', dict(config='private_fixture', section='main', values=dict(marker='changed')))[0] == 6
            assert rpc(sid, 'uci', 'commit', dict(config='private_fixture'))[0] == 6
            assert run('docker', 'exec', container, 'uci', '-q', 'get', 'private_fixture.main.marker').strip() == 'unchanged'
            assert denied(rpc('0'*32, 'uci', 'commit', dict(config='unisoc_modem')))
            print(f'PASS {repo.name}: old HTTP commit denied; 134/152/default/repeat persist; fresh session reads; unrelated config and unauthenticated writes denied')
        except Exception:
            subprocess.run(['docker', 'logs', container], timeout=10)
            subprocess.run(['docker', 'exec', container, '/bin/sh', '-c',
                            'cat /tmp/ubusd.log /tmp/rpcd.log /tmp/http.log 2>/dev/null; ubus list; cat /etc/config/rpcd'], timeout=10)
            raise
        finally:
            subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, check=True, timeout=30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--peer', type=Path)
    parser.add_argument('--image', default='mu300-openwrt-base:25.12.5')
    args = parser.parse_args()
    for repository in [TOP] + ([args.peer.resolve()] if args.peer else []):
        check(repository, args.image)
