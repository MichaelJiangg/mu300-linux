"""Magisk TF installer language follows the active Android locale."""
import os
import subprocess
import unittest

from helpers import TOP


class TfInstallerLocale(unittest.TestCase):
    def test_locale_detection_and_fallback(self):
        script = TOP / 'android/magisk/mu300-openwrt-tf/locale.sh'
        shell = '''
getprop() {
    case "$1" in
        persist.sys.locale) printf '%s' "$TEST_PERSIST_LOCALE" ;;
        persist.sys.locales) printf '%s' "$TEST_PERSIST_LOCALES" ;;
        persist.sys.language) printf '%s' "$TEST_PERSIST_LANGUAGE" ;;
        ro.product.locale) printf '%s' "$TEST_PRODUCT_LOCALE" ;;
        ro.product.locale.language) printf '%s' "$TEST_PRODUCT_LANGUAGE" ;;
    esac
}
. "$1"
mu300_install_lang
'''
        cases = (
            ({'TEST_PERSIST_LOCALE': 'zh-CN', 'TEST_PRODUCT_LOCALE': 'en-US'}, 'zh'),
            ({'TEST_PERSIST_LOCALE': 'zh-Hant-TW'}, 'zh'),
            ({'TEST_PERSIST_LOCALES': 'zh-CN,en-US'}, 'zh'),
            ({'TEST_PERSIST_LANGUAGE': 'zh', 'TEST_PRODUCT_LOCALE': 'en-US'}, 'zh'),
            ({'TEST_PRODUCT_LOCALE': 'zh-TW'}, 'zh'),
            ({'TEST_PERSIST_LOCALE': 'tr-TR', 'TEST_PRODUCT_LOCALE': 'zh-CN'}, 'en'),
            ({'TEST_PERSIST_LOCALE': 'en-US'}, 'en'),
            ({}, 'en'),
        )
        for props, want in cases:
            with self.subTest(props=props):
                env = dict(os.environ, TEST_PERSIST_LOCALE='', TEST_PERSIST_LOCALES='',
                           TEST_PERSIST_LANGUAGE='', TEST_PRODUCT_LOCALE='',
                           TEST_PRODUCT_LANGUAGE='')
                env.update(props)
                result = subprocess.run(['sh', '-c', shell, 'sh', str(script)], env=env,
                                        capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), want)

    def test_locale_file_is_in_magisk_package(self):
        builder = (TOP / 'tools/build-openwrt-tf-magisk.sh').read_text()
        customize = (TOP / 'android/magisk/mu300-openwrt-tf/customize.sh').read_text()
        self.assertIn('mu300-openwrt-tf/locale.sh', builder)
        self.assertIn('. "$MODPATH/locale.sh"', customize)
        self.assertIn('export MU300_INSTALL_LANG', customize)
        self.assertIn('MU300_INSTALLER_SHELLOPTS=$-', customize)
        self.assertIn('set +u', customize)


if __name__ == '__main__':
    unittest.main()
