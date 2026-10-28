"""openwrt/patches/luci-lexical-translator.sh (issue #376): LuCI's views keep their translations when a browser
extension puts Lodash on window._. The script gives luci.js's outer function a `const _` of its own, which the views
LuCI compiles there by direct eval() find before the global. A small stand-in for luci.js with the same opening and
the same way of compiling a view; the real luci.js was checked on a device (see the PR)."""
import json, shutil, subprocess, tempfile, unittest
from pathlib import Path
from helpers import TOP

SCRIPT = TOP / 'openwrt' / 'patches' / 'luci-lexical-translator.sh'
BUILD = TOP / 'openwrt' / 'build-rootfs.sh'

# luci.js as LuCI 25.12 ships it: a blank line, then the minified outer function; views are compiled with a direct
# eval() inside it (compileClass), so their free names resolve in this scope first
LUCI = ("\n((window,document,undefined)=>{'use strict';const env={};"
        "const compile=src=>eval('(function(window, document, L) { ' + src + ' })');"
        "window.mu300Compile=compile;})(window,document);")

# cbi.js's lookup: the trimmed string, its context before it with \\u0001, hashed (a stand-in hash here) into TR
CBI = r"""
var window = globalThis, document = {};
function trimws(s) { return String(s).trim().replace(/[ \t\n]+/g, ' '); }
function sfh(s) { return 'h:' + s; }
function _(s, c) { var k = (c != null ? trimws(c) + '\u0001' : '') + trimws(s); return (window.TR && TR[sfh(k)]) || s; }
window.TR = { 'h:Actions': 'Aktionen', 'h:menu\u0001Open': 'Offnen' };
"""


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the LuCI JS tests')
class LexicalTranslator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.js = self.tmp / 'luci.js'
        self.js.write_text(LUCI)

    def patch(self, ok=True):
        r = subprocess.run(['sh', str(SCRIPT), str(self.js)], capture_output=True, text=True)
        self.assertEqual(r.returncode == 0, ok, r.stderr)
        return r

    def run_page(self, lodash):
        prog = CBI + (
            "window._ = function lodash(v) { return { __wrapped__: v }; }; window._.VERSION = '4.17.21';\n"
            if lodash else '') + self.js.read_text() + r"""
const view = window.mu300Compile("return [ _('Actions'), _(' Actions\\n'), _('Open', 'menu'), _('Untranslated'), typeof _('Actions') ];");
console.log(JSON.stringify({ view: view(window, null, null), global: typeof window._('Actions') }));
"""
        r = subprocess.run(['node', '-e', prog], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_without_the_patch_lodash_breaks_the_view(self):
        self.assertEqual(self.run_page(True)['view'][4], 'object')

    def test_the_patched_view_translates_with_lodash_on_the_page(self):
        self.patch()
        out = self.run_page(True)
        self.assertEqual(out['view'], ['Aktionen', 'Aktionen', 'Offnen', 'Untranslated', 'string'])
        self.assertEqual(out['global'], 'object')       # the extension's window._ is left alone

    def test_the_patched_view_translates_without_lodash(self):
        self.patch()
        self.assertEqual(self.run_page(False)['view'][:4], ['Aktionen', 'Aktionen', 'Offnen', 'Untranslated'])

    def test_it_is_applied_once(self):
        self.patch()
        once = self.js.read_text()
        self.patch()
        self.assertEqual(self.js.read_text(), once)
        self.assertEqual(once.count('const _='), 1)
        subprocess.run(['node', '--check', str(self.js)], check=True)

    def test_an_unexpected_luci_js_fails_the_build(self):
        self.js.write_text("(function(window){'use strict';})(window);")
        self.patch(ok=False)
        self.assertNotIn('const _=', self.js.read_text())


class Build(unittest.TestCase):
    def test_the_image_build_applies_it(self):
        b = BUILD.read_text()
        self.assertIn('/in/luci-lexical-translator.sh:ro', b)
        self.assertIn('sh /in/luci-lexical-translator.sh $R/www/luci-static/resources/luci.js', b)


if __name__ == '__main__':
    unittest.main()
