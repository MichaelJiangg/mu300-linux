"""Exercise the shared hotplug component inside both CPU pages, no hardware."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import re
import argparse

TOP=Path(__file__).resolve().parents[2 if Path(__file__).parent.parent.name=='openwrt' else 1]
args=argparse.ArgumentParser()
args.add_argument('--peer',type=Path,help='Optional second repository to exercise the same component')
opts=args.parse_args()
APPS=[]
for repo in [TOP]+([opts.peer] if opts.peer else []):
    APPS.extend(p for p in (repo/'openwrt/luci-app-t551m',repo/'openwrt/luci-app-mu300') if p.is_dir())
chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=str(chrome) if chrome.exists() else None)
    for app in APPS:
        js=app/'htdocs/luci-static/resources'
        sources=[(js/f).read_text(encoding='utf-8') for f in ('mu300/common.js','mu300/cpu-cores.js','view/mu300/cpu.js')]
        for lang in ('zh-cn','en','tr'):
            for width in (360,1280):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content('<html><body></body></html>')
                page.add_style_tag(content='body{margin:12px;font-family:Arial}*{box-sizing:border-box}.mud-card{border:1px solid #ddd;border-radius:12px}.mud-btn{padding:8px 12px}')
                page.evaluate('''([sources,lang])=>{
                    window.L={env:{lang}}; window.requests=[];window.ticks=[];window.fail=false;
                    window.state={ok:1,persistent:false,boot_error:'',cores:[
                        {id:0,online:true,writable:false},{id:1,online:true,writable:true},
                        {id:2,online:true,writable:true},{id:3,online:true,writable:false}]};
                    const rpc={declare:spec=>(...args)=>{
                        if(spec.object!=='unisoc-cpu-cores')throw new Error('Unrelated RPC called');
                        if(spec.method==='apply'){
                            requests.push(args);
                            if(fail)return Promise.resolve({ok:0,error:'cpu_cores_write',rollback:true});
                            state.cores.forEach(c=>c.online=args[2]?true:args[0].find(v=>v.id===c.id).online);
                            state.persistent=args[2]?false:args[1];
                        }
                        return Promise.resolve(JSON.parse(JSON.stringify(state)));
                    }};
                    const baseclass={extend:x=>x},poll={add:f=>ticks.push(f)},view={extend:x=>x};
                    const M=new Function('rpc','baseclass','L',sources[0])(rpc,baseclass,L);
                    M.localizeMenu=()=>{};
                    const Cores=new Function('baseclass','rpc','poll','M',sources[1])(baseclass,rpc,poll,M);
                    window.cpuView=new Function('view','rpc','poll','M','Cores',sources[2])(view,rpc,poll,M,Cores);
                    const cpu={ok:1,available:true,persistent:false,policies:[],zones:[],voltage:{supported:false}};
                    document.body.append(cpuView.render(cpu));
                }''',[sources,lang])
                card=page.locator('.mud-cpu-cores')
                page.wait_for_selector('[data-core="2"]')
                assert card.locator('[data-core="0"]').is_disabled()
                assert card.locator('[data-core="0"]').is_checked()
                assert card.locator('[data-core="3"]').is_disabled()
                if lang!='zh-cn':assert not re.search(r'[\u4e00-\u9fff]',card.inner_text()),card.inner_text()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(app.name,lang,width)
                card.locator('[data-core="2"]').uncheck()
                card.locator('[data-core-persist]').check()
                page.evaluate('Promise.all(ticks.slice(0,1).map(f=>f()))')
                assert not card.locator('[data-core="2"]').is_checked(),'poll replaced unsaved edit'
                assert card.locator('[data-core-persist]').is_checked()
                card.locator('button.on').click()
                page.wait_for_function('requests.length===1 && !document.querySelector(".mud-cpu-cores button").disabled')
                request=page.evaluate('requests[0]')
                assert request==[[{'id':0,'online':True},{'id':1,'online':True},{'id':2,'online':False},{'id':3,'online':True}],True,False]
                assert card.locator('[data-core="0"]').is_disabled()
                assert card.locator('[data-core="3"]').is_disabled()
                # A rejection remains visible and does not strand the controls.
                page.evaluate('fail=true')
                card.locator('[data-core="1"]').uncheck()
                card.locator('button.on').click()
                page.wait_for_selector('.mud-core-error')
                assert not card.locator('[data-core="1"]').is_disabled()
                page.evaluate('fail=false')
                card.locator('button').nth(1).click()
                page.wait_for_function('requests.length===3 && !document.querySelector(".mud-cpu-cores button").disabled')
                assert card.locator('[data-core="2"]').is_checked()
                assert not card.locator('[data-core-persist]').is_checked()
                assert page.evaluate('requests[2][2]') is True
                assert not errors,errors
                page.close()
    browser.close()
print('PASS: both CPU pages, 3 languages, mobile/desktop layout, fixed cores, edit preservation, apply/persist/reset/error handling')
