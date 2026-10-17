"""Actual ucode patch/capability parsing and generated LuCI controls, offline."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from helpers import TOP

FEATURE=TOP/'openwrt/luci-app-mu300'
IMAGE=os.environ.get('MU300_WIFI_TEST_IMAGE')


@unittest.skipUnless(IMAGE and shutil.which('docker'),'MU300_WIFI_TEST_IMAGE required')
class UcodeCiphers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='mu300-ciphers-');cls.fixture=Path(cls.temp.name)
        cls.name='mu300-ciphers-'+uuid.uuid4().hex[:8]
        subprocess.run(['docker','run','-d','--network','none','--platform','linux/arm64','--name',cls.name,
            '-v',str(FEATURE/'root')+':/feature:ro','-v',str(cls.fixture)+':/fixture',
            '-v',str(FEATURE/'root/usr/libexec/unisoc-modem')+':/usr/libexec/unisoc-modem:ro',IMAGE,'sleep','3600'],check=True,stdout=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker','rm','-f',cls.name],check=True,stdout=subprocess.DEVNULL);cls.temp.cleanup()

    def run_ucode(self,*args):
        return subprocess.run(['docker','exec',self.name,'ucode',*args],capture_output=True,text=True,timeout=30)

    def test_parse_real_suite_ids_and_unknown_radio(self):
        program='''import { parse, capabilities } from '/usr/libexec/unisoc-modem/wifi-ciphers.uc';
const text='Supported Ciphers:\\n * CCMP-128 (00-0f-ac:4)\\n * GCMP-256 (00-0f-ac:9)\\nAvailable Antennas:\\n * fake (00-0f-ac:8)';
print(sprintf('%J', {suites:parse(text), unknown:capabilities('radio;reboot'), missing:capabilities('radio0')}));'''
        result=self.run_ucode('-e',program)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'suites':['00-0f-ac:4','00-0f-ac:9'],'unknown':{},'missing':{}})

    def test_actual_view_patch_idempotence_and_frontend(self):
        source=os.environ.get('MU300_WIFI_TEST_WIRELESS')
        if not source:self.skipTest('MU300_WIFI_TEST_WIRELESS required')
        target=self.fixture/'root/www/luci-static/resources/view/network/wireless.js';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(source).read_bytes())
        script='/feature/usr/libexec/unisoc-modem/filter-wifi-ciphers'
        result=self.run_ucode(script,'/fixture/root');self.assertEqual(result.returncode,0,result.stderr)
        first=target.read_bytes();result=self.run_ucode(script,'/fixture/root');self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(first,target.read_bytes())
        subprocess.run(['node','--check',str(target)],check=True)
        text=target.read_text();start=text.rfind('o=',0,text.index("'cipher',"));end=text.index('const crypto_modes',start)
        code=text[start:end]
        module=(FEATURE/'htdocs/luci-static/resources/mu300/wifi-ciphers.js').read_text()
        program='''const assert=require('assert');const [source,module]=JSON.parse(process.argv[1]);
// LuCI require() accepts constructors and instantiates them. A plain object
// works in an isolated helper test but breaks the complete wireless view.
const baseclass={extend(methods){function Module(){}Object.assign(Module.prototype,methods);return Module;}};
const exported=new Function('fs','L','_','baseclass',module)({}, {env:{lang:'zh-cn'}},x=>x,baseclass);
assert.strictEqual(typeof exported,'function','LuCI module must export a constructor');
const support=new exported();
const factory=new Function('ss','form','_','uci','mu300CipherSupport','mu300CipherCaps','let o;'+source+';return o;');
function controls(suites,saved='psk2') {const opt={keylist:[],vallist:[],depends(){},value(v,label){this.keylist.push(v);this.vallist.push(label)}};return factory({children:[{option:'encryption',write(){}}],taboption(){return opt}},{ListValue:{}},x=>x,{get(){return saved}},support,{suites});}
const native=controls(['00-0f-ac:2','00-0f-ac:4']);assert.deepStrictEqual(native.keylist,['auto','ccmp','tkip','tkip+ccmp']);assert.strictEqual(native.validate('id','ccmp'),true);
for(const c of ['gcmp','gcmp256','ccmp256']) {const old=controls(['00-0f-ac:4'],'sae+'+c);assert.strictEqual(old.cfgvalue('id'),c);assert(old.keylist.includes(c));assert.strictEqual(typeof old.validate('id',c),'string');old.cfgvalue('id');assert.strictEqual(old.keylist.filter(v=>v===c).length,1);assert.strictEqual(old.keylist.length,old.vallist.length);}
const other=controls(['00-0f-ac:4','00-0f-ac:8','00-0f-ac:9','00-0f-ac:10']);assert.deepStrictEqual(other.keylist,['auto','ccmp','ccmp256','gcmp','gcmp256']);assert.strictEqual(other.validate('id','gcmp'),true);
assert.strictEqual(controls(undefined).keylist.length,7);
'''
        subprocess.run(['node','-e',program,json.dumps([code,module])],check=True)
        # Removing the optional package must not leave a dangling LuCI import.
        result=self.run_ucode(script,'/fixture/root','--remove');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.read_bytes(),Path(source).read_bytes())
        result=self.run_ucode(script,'/fixture/root','--remove');self.assertEqual(result.returncode,0,result.stderr)

    def test_patch_failure_does_not_write_partial_view(self):
        target=self.fixture/'bad/www/luci-static/resources/view/network/wireless.js';target.parent.mkdir(parents=True,exist_ok=True);target.write_text("'use strict';unrecognized source")
        before=target.read_bytes();r=self.run_ucode('/feature/usr/libexec/unisoc-modem/filter-wifi-ciphers','/fixture/bad')
        self.assertNotEqual(r.returncode,0);self.assertEqual(before,target.read_bytes())

    def test_live_bus_without_radio_does_not_break_the_view(self):
        subprocess.run(['docker','exec',self.name,'sh','-c','mkdir -p /run /var/run/ubus; ubusd >/tmp/wifi-cipher-ubus.log 2>&1 &'],check=True)
        for _ in range(30):
            if subprocess.run(['docker','exec',self.name,'ubus','list'],capture_output=True).returncode==0:break
            time.sleep(.1)
        else:self.fail('Fixture ubus did not start')
        result=self.run_ucode('-e',"import { capabilities } from '/usr/libexec/unisoc-modem/wifi-ciphers.uc'; print(sprintf('%J', capabilities('radio0')));")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{})


if __name__=='__main__':unittest.main()
