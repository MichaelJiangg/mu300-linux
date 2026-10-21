"""Render the real LuCI patch view with dashboard CSS; no device or RPC writes."""
import asyncio
from pathlib import Path
import re
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
VIEW = (ROOT/'openwrt/luci-app-unisoc-ota/htdocs/luci-static/resources/view/system/unisoc-ota.js').read_text(encoding='utf-8')
ERRORS = (ROOT/'openwrt/luci-app-unisoc-ota/htdocs/luci-static/resources/unisoc-ota/errors.js').read_text(encoding='utf-8')
DASH = next(p for p in (ROOT/'openwrt').glob('luci-app-*/htdocs/luci-static/resources/mu300/common.js'))
CSS = re.search(r'var CSS = `([\s\S]*?)`;', DASH.read_text(encoding='utf-8'))[1]

RENDER = r"""async ({source,errors,css,dark,locale,pending})=>{
 document.documentElement.lang=locale;
 document.documentElement.style.cssText=dark?'--surface:#191e26;--background:#10141b;--text:#e9edf5;--text-muted:#a5adbc;--hairline:#343d4b;--brand:#64b0ff;--brand-subtle:#202e40;--on-brand:#102033;--success:#69cc92;--danger:#ff8d8d':'--surface:#fff;--background:#f5f7fa;--text:#202a38;--text-muted:#647185;--hairline:#dce2eb;--brand:#2563da;--brand-subtle:#edf3ff;--on-brand:#fff;--success:#22814b;--danger:#c13d3d';
 document.body.style.cssText='margin:0;padding:24px;font-family:system-ui,sans-serif;background:var(--background);color:var(--text)';
 document.body.innerHTML='';
 const style=document.createElement('style');style.textContent=css+' .test-overlay{position:fixed;inset:0;background:#0007;display:grid;place-items:center;padding:20px;z-index:1000}.test-modal{padding:24px;border-radius:14px;background:var(--surface);border:1px solid var(--hairline);max-width:520px;box-sizing:border-box;width:100%;box-shadow:0 20px 70px #0003}.test-modal h3{margin:0 0 18px}.test-modal .mud-btn{min-height:38px}';document.head.append(style);
 window.otaCalls=[];
 const state={identity:{version:'mu300-r20261021.115035-gb8d4f222-s581dc372'},transaction:{status:'complete'},recovery:{available:true,bytes:174555136,count:1},job:{status:'complete',result:{}},reboot_required:pending};
 const E=(tag,attrs={},children=[])=>{const e=document.createElement(tag);for(const [key,value] of Object.entries(attrs)){if(key==='click')e.addEventListener('click',value);else if(key==='disabled')e.disabled=value;else e.setAttribute(key,value);}for(const c of (Array.isArray(children)?children:[children]))if(c!=null)e.append(c instanceof Node?c:document.createTextNode(String(c)));return e;};
 const rpc={declare:({method})=>(...args)=>{window.otaCalls.push(method);if(method==='discard_recovery')state.recovery={available:false,bytes:0,count:0,deleted:true};return Promise.resolve(method==='status'?state:{});}};
 const ui={hideModal:()=>document.querySelector('.test-overlay')?.remove(),showModal:(title,children)=>{ui.hideModal();const box=E('div',{class:'test-modal',role:'dialog'},[E('h3',{},title),...children]);document.body.append(E('div',{class:'test-overlay'},[box]));},addNotification:()=>{},awaitReconnect:()=>{}};
 const messages=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(errors))));
 const v=new Function('view','rpc','ui','poll','E','document','L','M',source)({extend:x=>x},rpc,ui,{add(){},remove(){}},E,document,{hasViewPermission:()=>true},{injectCss(){},localizeMenu(){},uiLanguage:()=>locale});
 document.body.append(v.render([messages,state]));
}"""

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page()
        failures=[];page.on('pageerror',lambda e:failures.append(str(e)))
        for width in (1120,420,360):
            await page.set_viewport_size({'width':width,'height':900})
            for dark in (False,True):
                for locale in ('zh','en','tr'):
                    await page.evaluate(RENDER,dict(source=VIEW,errors=ERRORS,css=CSS,dark=dark,locale=locale,pending=False))
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,dark,locale)
                    text=await page.locator('.mud-ota-activity').inner_text()
                    assert 'Reboot to use' not in text and '请重启' not in text,text
                    if width==1120 and locale=='zh':
                        await page.screenshot(path=str(ROOT/('work/ota-luci-'+('dark' if dark else 'light')+'.png')))
        await page.evaluate(RENDER,dict(source=VIEW,errors=ERRORS,css=CSS,dark=True,locale='en',pending=True))
        assert 'Reboot to use' in await page.locator('.mud-ota-activity').inner_text()
        await page.get_by_role('button',name='Delete recovery copy',exact=True).click()
        assert 'discard_recovery' not in await page.evaluate('window.otaCalls')
        assert 'can no longer be undone' in await page.locator('.test-modal').inner_text()
        await page.get_by_role('button',name='Cancel',exact=True).click()
        assert 'discard_recovery' not in await page.evaluate('window.otaCalls')
        await page.get_by_role('button',name='Delete recovery copy',exact=True).click()
        await page.locator('.test-modal').get_by_role('button',name='Delete recovery copy',exact=True).click()
        await page.wait_for_function("window.otaCalls.includes('discard_recovery')")
        assert await page.get_by_role('button',name='Delete recovery copy',exact=True).is_disabled()
        assert await page.get_by_role('button',name='Roll back last patch',exact=True).is_disabled()
        assert not await page.get_by_role('button',name='Import patch',exact=True).is_disabled()
        assert not failures,failures
        await browser.close()
        print('PASS: dashboard CSS, 18 responsive/theme/language layouts, reboot status and confirmed deletion')

if __name__=='__main__':asyncio.run(main())
