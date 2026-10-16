"""TF formatting uses the full selected partition without a size cap."""
import unittest

from helpers import TOP


class TfFormatSize(unittest.TestCase):
    def test_filesystem_uses_full_selected_partition(self):
        script = (TOP / 'tools/android-install.sh').read_text()
        self.assertIn('if [ -x /system/bin/mke2fs ]; then', script)
        self.assertIn('/system/bin/mke2fs -t ext4 -F -b 4096', script)
        self.assertIn('-L mu300sd "$R" ||', script)
        self.assertNotIn('8388608', script)
        self.assertNotIn('32 GiB maximum', script)
        self.assertIn('full selected partition capacity', script)


if __name__ == '__main__':
    unittest.main()
