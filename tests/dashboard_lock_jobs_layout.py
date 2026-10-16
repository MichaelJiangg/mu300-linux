"""Real lock-page wiring with deferred capabilities and isolated fake RPC."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

RES = Path(__file__).resolve().parents[1] / 'openwrt/luci-app-mu300/htdocs/luci-static/resources'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({'executable_path': args.browser} if args.browser else {}))
        for lang in ('zh', 'en', 'tr'):
            page = browser.new_page(viewport={'width':390,'height':844})
            page.route('**/*', lambda route: route.abort())
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_content('<html><body><main id="app"></main></body></html>')
            page.evaluate('''([common,locks,lang]) => {
                const base={extend:x=>x};
                const L={env:{lang},resolveDefault:(p)=>p.catch(()=>null)};
                let first=true;
                window.calls=[];
                window.state={mode:{label:'auto'},auto_apply:1,endc:'1',cells:[],
                    caps:{nr:'1,5,6,8,28,41,78',lte:'1,3'},write_caps:{nr:'1,5,8,28,41,78',lte:'1,3'}};
                const rpc={declare:o=>(...args)=>{
                    calls.push([o.method,args]);
                    if(o.method==='lock_get') {
                        if(first) {first=false;return new Promise(r=>window.deliverCaps=r);}
                        if(window.holdRefresh) return new Promise(r=>window.deliverRefresh=r);
                        return Promise.resolve(window.state);
                    }
                    if(o.method==='lock_set') return Promise.resolve({ok:1,id:'abcdefghij',kind:args[0]});
                    if(o.method==='lock_status') return new Promise(r=>window.deliverJob=r);
                    return Promise.resolve({});
                }};
                const M=new Function('rpc','baseclass','L',common)(rpc,base,L);
                M.watchSms=()=>{}; M.confirmBox=()=>Promise.resolve(true);
                window.M=M;
                window.view=new Function('view','M','L','R',locks)(base,M,L,{poll:()=>()=>{}});
                document.querySelector('#app').appendChild(view.render());
            }''', [(RES/'mu300/common.js').read_text(encoding='utf-8'),
                   (RES/'view/mu300/locks.js').read_text(encoding='utf-8'), lang])
            assert page.locator('#mud-lock-nr-apply').is_disabled()
            assert page.locator('#mud-lock-lte-apply').is_disabled()
            assert page.locator('#mud-lock-nr .mud-chip').count() == 0
            page.evaluate('deliverCaps(state)')
            page.wait_for_function("!document.querySelector('#mud-lock-nr-apply').disabled")
            assert page.locator('#mud-lock-nr [data-b="6"]').count() == 0
            page.locator('#mud-lock-auto-apply').click()
            page.wait_for_function('!!window.deliverJob')
            assert page.evaluate('view._applying')
            assert page.evaluate("calls.filter(c=>c[0]==='lock_set').length") == 1
            page.evaluate("state.auto_apply=0; deliverJob({id:'abcdefghij',state:'done',ok:1})")
            page.wait_for_function('!view._applying')
            assert not page.locator('#mud-lock-auto-apply').evaluate("e=>e.classList.contains('on')")
            # A rejected second operation clears busy state and restores readback.
            page.locator('#mud-lock-auto-apply').click()
            page.wait_for_function("calls.filter(c=>c[0]==='lock_status').length===2")
            page.evaluate("deliverJob({id:'abcdefghij',state:'error',ok:0,error:'模组拒绝了设置'})")
            page.wait_for_function('!view._applying')
            assert not page.locator('#mud-lock-auto-apply').evaluate("e=>e.classList.contains('on')")
            # Mode buttons preserve their child spinner when paint() replaces
            # className; completion must remove it even if 'busy' disappeared.
            for mode, outcome in (('4g','done'), ('sa','error'), ('sa','done')):
                previous = page.evaluate("calls.filter(c=>c[0]==='lock_status').length")
                button = page.locator('#mud-lock-modes [data-mode="' + mode + '"]')
                button.click()
                page.wait_for_function("n=>calls.filter(c=>c[0]==='lock_status').length>n", arg=previous)
                assert button.locator('.mud-spin').count() == 1
                page.evaluate('''([mode,outcome]) => {
                    if(outcome==='done') state.mode.label=mode;
                    deliverJob({id:'abcdefghij',state:outcome,ok:outcome==='done'?1:0,error:'模组拒绝了设置'});
                }''', [mode, outcome])
                page.wait_for_function('!view._applying')
                assert button.locator('.mud-spin').count() == 0, (lang, mode, outcome, 'orphan spinner')
                assert not button.evaluate("e=>e.classList.contains('busy')")
            # A pending display refresh is independent of the completed job.
            page.evaluate('window.holdRefresh=true')
            previous = page.evaluate("calls.filter(c=>c[0]==='lock_status').length")
            button = page.locator('#mud-lock-modes [data-mode="4g"]')
            button.click()
            page.wait_for_function("n=>calls.filter(c=>c[0]==='lock_status').length>n", arg=previous)
            page.evaluate("state.mode.label='4g'; deliverJob({id:'abcdefghij',state:'done',ok:1})")
            page.wait_for_function('!!window.deliverRefresh')
            assert not page.evaluate('view._applying')
            assert button.locator('.mud-spin').count() == 0
            page.evaluate('holdRefresh=false; deliverRefresh(state)')
            # The shared helper also repairs spinners orphaned by other views.
            assert page.evaluate('''() => {
                const b=document.createElement('button'); b.textContent='label';
                M.busy(b,true); b.className='mud-btn on'; M.busy(b,true);
                if(b.querySelectorAll('.mud-spin').length!==1) return false;
                b.className='mud-btn on'; M.busy(b,false); M.busy(b,false);
                if(b.querySelector('.mud-spin')||b.classList.contains('busy')||b.textContent!=='label') return false;
                M.busy(b,true); b.textContent='new label'; M.busy(b,true);
                return b.querySelectorAll('.mud-spin').length===1;
            }''')
            assert not errors, (lang, errors)
            page.close()
        browser.close()
    print('Lock UI: deferred capabilities, task success/failure, busy reset and state restoration in 3 locales OK')


if __name__ == '__main__':
    main()
