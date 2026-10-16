"""Client lists share their own responsive row, not the device/SIM column."""
import json
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from helpers import TOP


HOME = TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/home.js'
COMMON = TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js'


class Layout(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.ids = {}

    def handle_starttag(self, tag, attrs):
        node = dict(attrs)
        node['parent'] = self.stack[-1] if self.stack else None
        if 'id' in node:
            if node['id'] in self.ids:
                raise AssertionError('duplicate id: ' + node['id'])
            self.ids[node['id']] = node
        if tag not in ('br', 'hr', 'input', 'img', 'meta', 'link'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        self.stack.pop()


@unittest.skipUnless(shutil.which('node'), 'Node.js required')
class DashboardLayout(unittest.TestCase):
    def test_lists_are_sibling_columns_below_device_details(self):
        js = """
const fs = require('fs');
const home = new Function('view', 'uci', 'M', fs.readFileSync(process.argv[2], 'utf8'))(
  { extend: obj => obj }, {}, {});
process.stdout.write(JSON.stringify(home.html()));
"""
        result = subprocess.run(['node', '-', str(HOME)], input=js, capture_output=True,
                                text=True, encoding='utf-8', check=True)
        layout = Layout()
        layout.feed(json.loads(result.stdout))
        clients = layout.ids['mud-clist']['parent']
        leases = layout.ids['mud-leases']['parent']
        self.assertIsNot(clients, leases)
        self.assertIs(clients['parent'], leases['parent'])
        self.assertIn('mud-client-cols', clients['parent']['class'].split())
        self.assertIs(layout.ids['mud-wcl']['parent']['parent'], clients)
        self.assertIs(layout.ids['mud-wleases']['parent']['parent'], leases)
        self.assertIsNot(layout.ids['mud-model']['parent']['parent']['parent'], clients)
        self.assertIsNot(layout.ids['mud-model']['parent']['parent']['parent'], leases)
        self.assertEqual(layout.stack, [])
        self.assertIs(layout.ids['mud-fwos']['parent']['parent'],
                      layout.ids['mud-lanip']['parent']['parent'])
        ids = list(layout.ids)
        self.assertEqual(ids[ids.index('mud-lanip') + 1], 'mud-fwos')

    def test_layout_can_shrink_and_wrap_long_device_names(self):
        css = COMMON.read_text(encoding='utf-8')
        self.assertIn('minmax(min(100%,300px),1fr)', css)
        self.assertIn('.mud-client-cols>div{min-width:0}', css)
        self.assertIn('.mud-client-cols .mud-cli .t{flex-wrap:wrap;overflow-wrap:anywhere}', css)
        self.assertIn('.mud-client-cols .mud-cli .s{overflow-wrap:anywhere}', css)


if __name__ == '__main__':
    unittest.main()
