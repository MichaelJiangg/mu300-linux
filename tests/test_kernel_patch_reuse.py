"""Run the real build patch loop twice with overlapping patches, without a kernel build."""
import difflib
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP


@unittest.skipUnless(shutil.which('bash') and shutil.which('patch'), 'bash and patch required')
class PatchLedger(unittest.TestCase):
    def test_overlap_repeat_and_changed_patch_failure(self):
        source = (TOP / 'upstream/build.sh').read_text()
        loop = source[source.index('for p in /work/patches/'):source.index('\nO=/src/out-')]
        with tempfile.TemporaryDirectory(prefix='mu300-patch-ledger-') as tmp:
            root = Path(tmp)
            patches = root / 'patches'; patches.mkdir()
            (root / 'sample').write_text('original\n')

            def make_patch(name, old, new):
                path = patches / name
                path.write_text(''.join(difflib.unified_diff([old + '\n'], [new + '\n'],
                                                           fromfile='a/sample', tofile='b/sample')))
                return path

            first = make_patch('0001.patch', 'original', 'intermediate')
            make_patch('0002.patch', 'intermediate', 'final')
            script = 'set -e\nKV=7.2.8\n' + loop.replace('/work/patches', str(patches))
            def run():
                return subprocess.run(['bash', '-c', script], cwd=root, capture_output=True, text=True)
            for _ in range(2):
                result = run()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / 'sample').read_text(), 'final\n')
                self.assertEqual(len((root / '.mu300-patches').read_text().splitlines()), 2)
            # A changed patch must not silently count as applied because its name was recorded.
            old_ledger = (root / '.mu300-patches').read_bytes()
            make_patch('0001.patch', 'original', 'different')
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('patch does not apply', result.stderr)
            self.assertEqual((root / '.mu300-patches').read_bytes(), old_ledger)
            self.assertNotIn(hashlib.sha256(first.read_bytes()).hexdigest(), old_ledger.decode())
