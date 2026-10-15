"""Serial-bound ADB operations. Frontend never supplies shell text."""
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import time

from .state import sha
from .diagnostics import traced


def hidden_process():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


class Adb:
    def __init__(self, package, serial=None):
        self.serial = serial
        names = ('tools/adb.exe', 'platform-tools/adb.exe') if os.name == 'nt' else ('tools/macos/adb', 'tools/adb', 'platform-tools/adb', 'tools/adb.exe')
        paths = [Path(package) / name for name in names]
        self.exe = next((str(p) for p in paths if p.is_file()), shutil.which('adb'))
        if not self.exe:
            raise ValueError('ADB is missing from tools / 安装包缺少 ADB 工具')
        self.su = None
        self.context = None
        self.backup_staging = None

    def call(self, *args, timeout=20, check=True):
        cmd = [self.exe]
        if self.serial and args[0] != 'devices':
            cmd += ['-s', self.serial]
        def perform():
            result = subprocess.run(cmd + list(args), capture_output=True, timeout=timeout, **hidden_process())
            if check and result.returncode:
                detail = (result.stderr or result.stdout).decode('utf-8', 'replace')[-4000:].strip()
                raise ConnectionError('ADB command failed / ADB 命令失败'+(': '+detail if detail else ''))
            return result.stdout.decode('utf-8', 'replace').replace('\r', '')
        return traced(self.context, 'ADB '+shlex.join(list(args)), perform, output=True)

    def devices(self):
        result = []
        for line in self.call('devices', '-l').splitlines()[1:]:
            values = line.split()
            if len(values) >= 2:
                result.append({'serial': values[0], 'state': values[1],
                               'label': next((v[6:] for v in values[2:] if v.startswith('model:')), values[0][-4:])})
        return result

    def shell(self, script, root=False, timeout=20):
        if root and self.su is None:
            raise ValueError('Root has not been verified / 尚未验证 root')
        command = (self.su + ' -c ' if root and self.su else 'sh -c ') + shlex.quote(script)
        return self.call('shell', command, timeout=timeout)

    def root_status(self):
        if self.shell('id -u').strip() == '0':
            self.su = ''
            return 'ready'
        found = False
        for name in ('su', '/debug_ramdisk/su', '/sbin/su'):
            available = self.shell('command -v ' + name + ' >/dev/null 2>&1; echo $?').strip() == '0'
            if not available:
                continue
            found = True
            try:
                result = self.shell(name + ' -c id', timeout=8)
                if re.search(r'\buid=0\b', result):
                    self.su = name
                    return 'ready'
            except (ConnectionError, subprocess.TimeoutExpired):
                pass
        return 'root_permission' if found else 'magisk'

    def read(self, script):
        """Small binary metadata reads; partition backups use dd + adb pull."""
        if self.su is None:raise ValueError('Root has not been verified / 尚未验证 root')
        command=(self.su+' -c ' if self.su else 'sh -c ')+shlex.quote('stty raw -echo -onlcr 2>/dev/null || true; '+script)
        args=[self.exe]+(['-s',self.serial] if self.serial else [])+['exec-out',command]
        def perform():
            result=subprocess.run(args,capture_output=True,timeout=45,**hidden_process())
            if result.returncode or not result.stdout:
                raise ConnectionError('ADB metadata read failed / ADB 元数据读取失败')
            return result.stdout
        return traced(self.context,'ADB metadata read '+script,perform)

    def _backup_directory(self, context, total):
        free=int(self.shell("df -Pk /data/local/tmp | tail -n1 | awk '{print $4}'").strip())*1024
        if free<total+(64<<20):
            raise ValueError('Insufficient Android staging space for backup / Android 备份临时空间不足')
        if not self.backup_staging:
            self.backup_staging='/data/local/tmp/openwrt-backup-'+secrets.token_hex(12)
            # A shell-owned private directory lets adb pull read root-created
            # images without making the directory accessible to other apps.
            context.record['backup_staging']=self.backup_staging
            context.store.save(context.record)
            self.shell('umask 077; mkdir '+self.backup_staging)
        return self.backup_staging

    def _pull_backup(self, remote, local, total, name, context):
        args=[self.exe]+(['-s',self.serial] if self.serial else [])+['pull',remote,str(local)]
        since=time.monotonic();last_change=since;previous=-1
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**hidden_process())
        try:
            while True:
                context.boundary()
                try:
                    out,err=process.communicate(timeout=.1)
                    finished=True
                except subprocess.TimeoutExpired:
                    finished=False
                received=local.stat().st_size if local.exists() else 0
                if received>total:raise ValueError('Backup is larger than the selected partition / 备份大小超出分区范围')
                if received!=previous:
                    last_change=time.monotonic();previous=received
                    context.transfer('backup/'+name,received,total,since)
                if finished:
                    if process.returncode:
                        raise ConnectionError('ADB pull failed / ADB 拉取失败: '+err.decode('utf-8','replace')[-2000:])
                    context.log(out.decode('utf-8','replace')+err.decode('utf-8','replace'),scope='adb-pull')
                    if received!=total:raise ValueError('Incomplete backup / 备份文件不完整: '+name)
                    return
                if time.monotonic()-last_change>45:
                    raise TimeoutError('ADB pull received no data for 45 seconds / ADB 拉取 45 秒未收到数据')
        finally:
            if process.poll() is None:process.kill()
            process.communicate(timeout=5)

    def backup_partition(self, name, destination, context):
        if not re.fullmatch(r'(misc|(?:boot|uboot|sml|teecfg|trustos|vbmeta)_[ab])',name):
            raise ValueError('Unsupported backup partition')
        source='/dev/block/by-name/'+name
        total=4096 if name=='misc' else int(self.shell('blockdev --getsize64 '+source,root=True).strip())
        if total<=0:raise ValueError('Invalid backup partition size: '+name)
        remote=self._backup_directory(context,total)+'/'+name+'.img'
        local=Path(str(destination)+'.partial')
        context.log(f'Backing up {name}: {total} bytes; device dd -> adb pull',scope='backup')
        try:
            command=f'dd if={source} of={remote} bs=4M'
            if name=='misc':command=f'dd if={source} of={remote} bs=4096 count=1'
            self.shell('set -e; umask 077; '+command+'; chmod 644 '+remote,root=True,timeout=120)
            expected=self.shell('sha256sum '+remote,root=True,timeout=120).split()[0]
            original=f'dd if={source} bs=4096 count=1 2>/dev/null' if name=='misc' else 'cat '+source
            actual=self.shell('(set -o pipefail; '+original+') | sha256sum',root=True,timeout=120).split()[0]
            if not re.fullmatch('[a-f0-9]{64}',expected) or expected!=actual:
                raise ValueError('Device backup checksum mismatch / 设备临时备份校验失败: '+name)
            self._pull_backup(remote,local,total,name,context)
            if sha(local)!=expected:raise ValueError('Computer backup checksum mismatch / 电脑备份校验失败: '+name)
            with local.open('r+b') as stream:os.fsync(stream.fileno())
            os.replace(local,destination)
            context.log(f'Backup verified: {name}, {total} bytes, SHA256 {expected}',scope='backup')
        finally:
            try:self.shell('rm -f '+remote,root=True)
            except Exception as error:context.log('Backup staging cleanup: '+str(error),level='warning',scope='backup')
            if local.exists():local.unlink()

    def cleanup_backup(self, context):
        if not self.backup_staging:return
        try:
            self.shell('rmdir '+self.backup_staging)
            context.record.pop('backup_staging',None)
            context.store.save(context.record)
            self.backup_staging=None
        except Exception as error:
            context.log('Backup staging directory cleanup: '+str(error),level='warning',scope='backup')

    def properties(self):
        names = ('ro.product.model', 'ro.product.device', 'ro.board.platform', 'ro.boot.slot_suffix',
                 'ro.boot.verifiedbootstate', 'ro.crypto.state', 'ro.crypto.type', 'sys.boot_completed')
        result = {}
        for name in names:
            result[name] = self.shell('getprop ' + name).strip()
        return result


def push_chunks(adb_call, shell, local, remote, context):
    """Actual acknowledged bytes, checksum at destination, no terminal parsing."""
    import tempfile
    total = Path(local).stat().st_size
    since = time.monotonic()
    shell('rm -f ' + shlex.quote(remote))
    done = 0
    with open(local, 'rb') as stream, tempfile.TemporaryDirectory() as temp:
        chunk_path = Path(temp) / 'chunk'
        while chunk := stream.read(8 << 20):
            context.boundary()
            chunk_path.write_bytes(chunk)
            part = remote + '.upload-chunk'
            adb_call('push', str(chunk_path), part)
            if shell('sha256sum ' + shlex.quote(part)).split()[0] != sha(chunk_path):
                raise ValueError('Transfer chunk checksum failed / 传输块校验失败')
            shell('cat ' + shlex.quote(part) + ' >> ' + shlex.quote(remote) + ' && rm -f ' + shlex.quote(part))
            done += len(chunk)
            context.transfer(Path(local).name, done, total, since)
    if shell('sha256sum ' + shlex.quote(remote)).split()[0] != sha(local):
        raise ValueError('Transfer checksum failed / 传输校验失败')
    return remote
