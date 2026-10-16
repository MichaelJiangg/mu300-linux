"""Optional browser regression: real shared dialogs/CSS, isolated mock RPC."""
import importlib.util
import os
import unittest
from helpers import TOP

@unittest.skipUnless(os.environ.get('MU300_BROWSER_TESTS')=='1' and importlib.util.find_spec('playwright'), 'opt-in Playwright test')
class ApnUI(unittest.TestCase):
    def test_responsive_crud_and_confirmation(self):
        from playwright.sync_api import sync_playwright
        src=TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources'
        common=(src/'mu300/common.js').read_text(encoding='utf-8')
        apn=(src/'view/mu300/apn.js').read_text(encoding='utf-8')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel=os.environ.get('MU300_BROWSER_CHANNEL') or None,headless=True)
            page=browser.new_page(viewport={'width':390,'height':844})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/*',lambda r:r.abort())
            for lang in ('zh','en','tr'):
                page.set_content('<html><head></head><body style="margin:16px"></body></html>')
                page.evaluate('''({common,apn,lang})=>{
                    window.L={env:{lang},bind:(fn,ctx)=>fn.bind(ctx)};
                    window._=s=>s; window.N_=(a,b,n)=>n===1?a:b;
                    window.calls=[];
                    window.state={ok:1,data_sim:1,current:{apn:'',pdptype:'IPV4V6'},profiles:[{id:'automatic',name:'SIM default',apn:'',pdptype:'IPV4V6',current:true}]};
                    const rpc={declare:spec=>async(...args)=>{
                        if(spec.method==='apn_get')return JSON.parse(JSON.stringify(state));
                        if(spec.method!=='apn_set')return {};
                        if(window.failNext){window.failNext=false;return {ok:0,error:'apn_storage'};}
                        calls.push(args);let [action,payload]=args,p=JSON.parse(payload);
                        if(action==='save'){p.id=p.id||'p'+state.profiles.length;state.profiles=state.profiles.filter(x=>x.id!==p.id);state.profiles.push(p);}
                        if(action==='delete')state.profiles=state.profiles.filter(x=>x.id!==p.id);
                        if(action==='apply'){let q=state.profiles.find(x=>x.id===p.id);state.current={apn:q.apn,pdptype:q.pdptype};state.profiles.forEach(x=>x.current=x.id===p.id);}
                        return {ok:1};
                    }};
                    const M=new Function('rpc','baseclass',common)(rpc,{extend:x=>x});
                    const view=new Function('view','rpc','M',apn)({extend:x=>x},rpc,M);
                    window.M=M;window.apnView=view;document.body.append(view.render(state));
                }''',{'common':common,'apn':apn,'lang':lang})
                page.locator('.apn-head button').nth(1).click()
                page.locator('.mud-apn-editor input').nth(0).fill('Carrier <Test>')
                page.locator('.mud-apn-editor input').nth(1).fill('internet.example')
                page.locator('.mud-apn-editor select').nth(1).select_option('chap')
                page.locator('.mud-apn-editor input').nth(2).fill('fixture-account')
                self.assertEqual(page.locator('.mud-apn-editor input').nth(2).get_attribute('type'),'text')
                self.assertTrue(page.locator('.mud-apn-editor input').nth(2).evaluate('(e)=>parseFloat(getComputedStyle(e).paddingLeft)>=10 && parseFloat(getComputedStyle(e).borderTopWidth)>=1'))
                self.assertTrue(page.locator('.mud-dlg').evaluate('(e)=>e.getBoundingClientRect().top>=0 && e.getBoundingClientRect().bottom<=innerHeight'))
                page.locator('.mud-apn-editor input[type=password]').fill('fixture-secret')
                if lang!='zh':
                    self.assertNotIn('鉴权方式',page.locator('.mud-apn-editor').inner_text())
                    self.assertNotIn('初始附着',page.locator('.mud-apn-editor').inner_text())
                page.locator('.mud-dlg [data-r="1"]').click()
                page.wait_for_function('state.profiles.length===2 && !apnView.busy')
                self.assertEqual(page.evaluate('calls.length'),1)
                self.assertEqual(page.evaluate('JSON.parse(calls[0][1]).auth'),'chap')
                self.assertEqual(page.evaluate('JSON.parse(calls[0][1]).username'),'fixture-account')
                self.assertEqual(page.locator('.apn-item strong').nth(1).inner_text(),'Carrier <Test>')
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                page.locator('.apn-item').nth(1).locator('button').nth(0).click()
                page.locator('.mud-dlg [data-r="0"]').click()
                self.assertEqual(page.evaluate('calls.length'),1)
                page.locator('.apn-item').nth(1).locator('button').nth(0).click()
                page.locator('.mud-dlg [data-r="1"]').click()
                page.wait_for_function('calls.length===2 && !apnView.busy')
                self.assertTrue(page.evaluate('JSON.parse(calls[1][1]).remember'))
                self.assertTrue(page.locator('.apn-item').nth(1).locator('button').nth(2).is_disabled())
                page.locator('.apn-item').nth(0).locator('button').nth(2).click()
                page.locator('.mud-dlg [data-r="1"]').click()
                page.wait_for_function('state.profiles.length===1 && !apnView.busy')
                self.assertEqual(page.locator('.mud-dlg-wrap').count(),0)
                self.assertFalse(page.locator('.apn-actions button').nth(0).is_disabled())
                page.evaluate('window.failNext=true')
                page.locator('.apn-actions button').nth(1).click()
                page.locator('.mud-apn-editor input').nth(0).fill('Failed edit')
                page.locator('.mud-dlg [data-r="1"]').click()
                page.wait_for_function('!window.failNext && !apnView.busy')
                self.assertEqual(page.locator('.apn-item strong').inner_text(),'Carrier <Test>')
                self.assertFalse(page.locator('.apn-actions button').nth(1).is_disabled())
            self.assertEqual(errors,[])
            browser.close()
