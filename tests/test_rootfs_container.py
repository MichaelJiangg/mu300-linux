"""Keep the rootfs assembly inside one complete container shell argument."""
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'openwrt/build-rootfs.sh'

class ContainerCommand(unittest.TestCase):
    def test_complete_assembly_is_one_shell_argument(self):
        text=SCRIPT.read_text()
        start=text.index('docker run --rm --platform linux/arm64 \\\n')
        end=text.index("ls -la /out/$OUT'",start)+len("ls -la /out/$OUT'")
        tokens=shlex.split(text[start:end])
        index=tokens.index('/bin/sh')
        self.assertEqual(tokens[index+1:index+3],['-eu','-c'])
        self.assertEqual(len(tokens[index:]),4,'assembly escaped the container command')
        body=tokens[-1]
        self.assertIn('command -v flock >/dev/null',body)
        self.assertIn('cp /in/mainline-modules/*.ko',body)
        self.assertIn('tar -czf /out/$OUT .',body)
        self.assertTrue(body.endswith('ls -la /out/$OUT'))
        if shutil.which('sh'):
            result=subprocess.run(['sh','-n'],input=body,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
