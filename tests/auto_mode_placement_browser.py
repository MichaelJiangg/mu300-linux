"""Real lock-page wiring and compatibility/UCI sequencing with isolated RPC."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import argparse,re

TOP=Path(__file__).resolve().parents[2 if Path(__file__).parent.parent.name=='openwrt' else 1]
ap=argparse.ArgumentParser();ap.add_argument('--peer',type=Path);args=ap.parse_args()
apps=[]
for repo in [TOP]+([args.peer] if args.peer else []):
    apps.extend(p for p in (repo/'openwrt/luci-app-t551m',repo/'openwrt/luci-app-mu300') if p.is_dir())
chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
cases=0
with sync_playwright() as p:
    browser=p.chromium.launch(**({'executable_path':str(chrome)} if chrome.exists() else {}))
    for app in apps:
        js=app/'htdocs/luci-static/resources'
        assert 'auto_work_mode' not in (js/'view/mu300/settings.js').read_text(encoding='utf-8')
        sources=[(js/f).read_text(encoding='utf-8') for f in ('mu300/common.js','mu300/auto-mode.js','view/mu300/locks.js')]
        for default in ('134','152'):
            for lang in ('zh-cn','en','tr'):
                for width in (360,1280):
                    page=browser.new_page(viewport={'width':width,'height':900})
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.set_content('<html><body><main></main></body></html>')
                    page.add_style_tag(content='body{margin:12px;font-family:Arial}*{box-sizing:border-box}main{max-width:1080px;margin:auto;min-width:0}')
                    page.evaluate('''([sources,lang,defaultMode])=>{
                        const base={extend:x=>x},L={env:{lang},resolveDefault:p=>p.catch(()=>null)};
                        window.slot='0';window.calls=[];window.notes=[];window.failSet=false;window.failCommit=false;window.holdCommit=false;
                        window.cfg={auto_work_mode:'152',auto_work_mode_default:defaultMode,data_sim:'0',at_port:'/dev/test'};
                        window.state={ts:1,mode:{label:'4g'},auto_apply:1,endc:'1',cells:[],caps:{nr:'1,78',lte:'1,3'},write_caps:{nr:'1,78',lte:'1,3'}};
                        const rpc={declare:spec=>(...args)=>{
                            if(spec.object==='uci'){
                                calls.push([spec.method,...args]);
                                if(spec.method==='get')return Promise.resolve({...cfg});
                                if(spec.method==='set'){
                                    if(failSet)return Promise.reject(new Error('set failed'));
                                    Object.assign(cfg,args[2]);return Promise.resolve({});
                                }
                                if(spec.method==='commit'){
                                    if(failCommit)return Promise.reject(new Error('commit failed'));
                                    if(holdCommit)return new Promise(r=>window.releaseCommit=r);
                                    return Promise.resolve({});
                                }
                            }
                            return Promise.resolve({});
                        }};
                        const M=new Function('rpc','baseclass','L',sources[0])(rpc,base,L);
                        M.watchSms=()=>{};M.simSelector=()=>{};M.simSlot=M.selectedSlot=()=>slot;
                        M.confirmBox=()=>new Promise(r=>window.confirmAuto=r);
                        M.callLockSet=(kind,value)=>{
                            calls.push(['lock',kind,value,slot]);state.mode.label=value;
                            return Promise.resolve({ok:1,id:'abcdefghij',kind});
                        };
                        M.waitLockJob=()=>Promise.resolve({ok:1,state:'done'});
                        M.callLockGet=()=>Promise.resolve(state);
                        const AutoMode=new Function('baseclass','rpc','M',sources[1])(base,rpc,M);
                        window.view=new Function('view','M','L','R','poll','AutoMode',sources[2])(
                            base,M,L,{poll:()=>()=>{}},{add(){},remove(){}},AutoMode);
                        view.note=(text,type)=>notes.push([text,type]);
                        view.refresh=function(){this.lastLock=state;this.paint();return Promise.resolve();};
                        view.loadServing=view.loadServingMeta=()=>Promise.resolve();
                        view.paintServing=view.paintNeighbors=()=>{};
                        document.querySelector('main').append(view.render());
                    }''',[sources,lang,default])
                    select=page.locator('#mud-auto-mode-select');button=page.locator('#mud-auto-mode button')
                    page.wait_for_function('document.querySelector("#mud-auto-mode-select").options.length===3')
                    assert page.locator('#mud-auto-mode').is_hidden()
                    assert select.input_value()=='152'
                    assert default in select.locator('option').first.inner_text()
                    page.evaluate("state.mode.label='auto';view.paint()")
                    assert select.is_visible()
                    if lang!='zh-cn':assert not re.search(r'[\u4e00-\u9fff]',page.locator('#mud-auto-mode').inner_text())
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(app.name,lang,width)
                    select.select_option('134');page.evaluate('view.paint()')
                    assert select.input_value()=='134'
                    assert page.evaluate('calls.filter(c=>c[0]!=="get").length')==0
                    button.click();page.evaluate('confirmAuto(false)')
                    assert page.evaluate('calls.filter(c=>c[0]!=="get").length')==0
                    # A slow save must finish before any mode operation. A SIM
                    # switch during that wait cannot apply to the wrong slot.
                    page.evaluate('holdCommit=true')
                    button.click();page.evaluate('confirmAuto(true)')
                    page.wait_for_function('!!window.releaseCommit')
                    assert page.evaluate('calls.filter(c=>c[0]==="lock").length')==0
                    page.evaluate("slot='1';holdCommit=false;releaseCommit({})")
                    page.wait_for_function('!view._applying')
                    assert page.evaluate('calls.filter(c=>c[0]==="lock").length')==0
                    # Successful application changes only the compatibility
                    # option and follows the pre-existing auto-mode job once.
                    page.evaluate("slot='0';calls=[]")
                    select.select_option('default');button.click();page.evaluate('confirmAuto(true)')
                    page.wait_for_function('!view._applying && calls.some(c=>c[0]==="lock")')
                    assert page.evaluate('calls')==[
                        ['set','unisoc_modem','main',{'auto_work_mode':'default'}],
                        ['commit','unisoc_modem'],['lock','mode','auto','0']]
                    assert page.evaluate('cfg.data_sim')=='0'
                    assert page.evaluate('cfg.at_port')=='/dev/test'
                    assert page.evaluate('cfg.auto_work_mode_default')==default
                    # Failed commits and failed setters never invoke AT.
                    for failing in ('failSet','failCommit'):
                        page.evaluate(f'calls=[];{failing}=true')
                        select.select_option('152');button.click();page.evaluate('confirmAuto(true)')
                        page.wait_for_function('!view._applying && calls.length>0')
                        assert page.evaluate('calls.filter(c=>c[0]==="lock").length')==0
                        assert not button.is_disabled()
                        page.evaluate(f'{failing}=false')
                    # Other network modes retain their original path; hiding
                    # this control must not erase the saved compatibility.
                    page.evaluate('calls=[]')
                    page.locator('#mud-lock-modes [data-mode="4g"]').click();page.evaluate('confirmAuto(true)')
                    page.wait_for_function('!view._applying && state.mode.label==="4g"')
                    assert page.locator('#mud-auto-mode').is_hidden()
                    assert page.evaluate('calls')==[['lock','mode','4g','0']]
                    assert page.evaluate('cfg.auto_work_mode')=='152'
                    assert not errors,errors
                    page.close();cases+=1
    browser.close()
print(f'PASS {cases} lock-page cases: placement/visibility/defaults/translations/drafts/cancel/UCI failure/SIM-switch guard/ordered single-job apply')
