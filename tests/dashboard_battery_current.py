"""Render signed net battery current in the real homepage at both screen sizes."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
JS=ROOT/'openwrt/luci-app-mu300/htdocs/luci-static/resources'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser');args=parser.parse_args()
    common=(JS/'mu300/common.js').read_text(encoding='utf-8')
    home=(JS/'view/mu300/home.js').read_text(encoding='utf-8')
    count=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**({'executable_path':args.browser} if args.browser else {}))
        for lang in ('zh','en','tr'):
            for width in (390,1280):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content('<html><body><main></main></body></html>')
                page.evaluate("""([common,home,lang])=>{
                    const base={extend:x=>x},L={env:{lang}};
                    window.M=new Function('rpc','baseclass','L',common)({declare:()=>()=>Promise.resolve({})},base,L);
                    window.app=new Function('view','uci','R','M','SimRadio',home)(base,{}, {},M,{});
                    M.injectCss();app._root=document.querySelector('main');app._root.className='mud';
                    app._root.innerHTML=app.html();
                }""",[common,home,lang])
                for current,expected in [(260000,'+260mA'),(-570000,'-570mA'),(0,'0mA'),(None,'--')]:
                    # A plugged-in dock can still discharge the battery: sign
                    # follows the actual measurement, never USB or status.
                    page.evaluate("p=>app.update({info:{power:p}})",dict(present=1,capacity=73,status='Charging',volt=3.94,ua=current,usb=1))
                    assert page.locator('#mud-batt-l').inner_text()=='Charging · 3.94 V · '+expected+' · USB'
                    assert page.locator('#mud-batt-meter').is_visible()
                    assert page.locator('#mud-batt-bar').evaluate('el=>el.style.width')=='73%'
                    count+=1
                page.evaluate("app.update({info:{power:{present:0,ua:999999,usb:1}}})")
                assert 'mA' not in page.locator('#mud-batt-l').inner_text()
                assert page.locator('#mud-batt').inner_text()=='USB'
                assert not page.locator('#mud-batt-meter').is_visible()
                page.evaluate("app.update({info:{power:{present:1,capacity:73,ua:800000}}})")
                assert page.locator('#mud-batt-l').inner_text()=='-- · +800mA'
                assert page.locator('#mud-batt-meter').is_visible()
                for cap,width in [(0,'0%'),(100,'100%'),(None,'0%')]:
                    page.evaluate('cap=>app.update({info:{power:{present:1,capacity:cap}}})',cap)
                    assert page.locator('#mud-batt-bar').evaluate('el=>el.style.width')==width
                    assert page.locator('#mud-batt-meter').is_visible()==(cap is not None)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                count+=2;page.close()
        browser.close()
    print('PASS',count,'battery current cases, three languages, mobile/desktop')
if __name__=='__main__':main()
