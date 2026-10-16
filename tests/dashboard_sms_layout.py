"""Offline rendering smoke test. Requires Python Playwright and a local browser.

Run explicitly: python tests/dashboard_sms_layout.py [--browser PATH]
No router, modem, external URL or saved browser profile is used.
"""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

TOP = Path(__file__).resolve().parents[1]
RES = TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser')
    args = parser.parse_args()
    common = (RES / 'mu300/common.js').read_text(encoding='utf-8')
    sms = (RES / 'view/mu300/sms.js').read_text(encoding='utf-8')
    css = (RES / 'view/mu300/sms.css').read_text(encoding='utf-8')
    checked = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({'executable_path': args.browser} if args.browser else {}))
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('<html><head></head><body><main id="app"></main></body></html>')
        page.evaluate('''([common, refresh, home]) => {
            window.calls = {status:0,rates:0};
            const L = {env:{lang:'en'},resolveDefault:(p,d)=>Promise.resolve(p).catch(()=>d)};
            const rpc = {declare:spec=>()=>{
                if (spec.method==='status') { calls.status++; return Promise.resolve({info:{ts:1,host:'test'},cell:null}); }
                if (spec.method==='rates') { calls.rates++; return Promise.resolve({available:true,device:'cell0',ifindex:1,boot_id:'a',ts:performance.now()/1000,rx:calls.rates*1000,tx:calls.rates*500}); }
                return Promise.resolve({});
            }};
            const base={extend:x=>x};
            const M=new Function('rpc','baseclass','L',common)(rpc,base,L); M.watchSms=()=>{};
            const R=new Function('baseclass',refresh)(base);
            const view=new Function('view','uci','R','M','L',home)(base,{load:()=>Promise.resolve(),get:()=>2},R,M,L);
            document.querySelector('#app').appendChild(view.render());
        }''', [common, (RES / 'mu300/refresh.js').read_text(encoding='utf-8'),
               (RES / 'view/mu300/home.js').read_text(encoding='utf-8')])
        page.wait_for_function("calls.status >= 2 && calls.rates >= 3 && document.querySelector('#mud-dl').textContent.includes('/s')")
        assert page.inner_text('#mud-host') == 'test'
        calls = page.evaluate('() => {document.querySelector(".mud").remove(); return {...calls};}')
        page.wait_for_timeout(2200)
        assert page.evaluate('calls') == calls, 'removed home view kept polling'
        page.close()
        print('Home render: separate live counters and detached-view cleanup passed')
        for width in (390, 1280):
            for theme in ('bootstrap', 'aurora'):
                for dark in (False, True):
                    for lang in ('zh', 'en', 'tr'):
                        page = browser.new_page(viewport={'width': width, 'height': 900})
                        page.route('**/*', lambda route: route.abort())
                        page.set_content('<html><head></head><body><main id="app"></main></body></html>')
                        background, text = ('#202226', '#eeeeee') if dark else ('#ffffff', '#222222')
                        variables = (f'--surface:{background};--text:{text};--hairline:#777;--brand:#467bef;' if theme == 'aurora' else
                                     f'--background-color-high:{background};--background-color-low:{background};--text-color-high:{text};--border-color-low:#777;--primary-color-high:#467bef;')
                        page.add_style_tag(content=f'html{{{variables}}}body{{margin:0;padding:12px;background:{background};font-family:sans-serif}}main{{max-width:1050px;margin:auto;min-width:0}}')
                        page.evaluate('''([common, sms, lang]) => {
                            const L = { env:{lang}, resource:s => 'https://offline.invalid/' + s };
                            const M = new Function('rpc','baseclass','L',common)({declare:()=>()=>{}},{extend:x=>x},L);
                            M.watchSms = () => {};
                            const E = (tag, attrs) => {const e=document.createElement(tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e;};
                            const view = new Function('view','M','E','L',sms)({extend:x=>x},M,E,L);
                            view.wire = () => {}; view.reload = () => {};
                            document.querySelector('#app').appendChild(view.render());
                            document.querySelector('#mud-sms-num').value = '+90555123456789012345678901234567890';
                            document.querySelector('#mud-sms-convs').innerHTML = '<div class="mud-conv"><div class="n">+90555123456789012345678901234567890</div><div class="p">long-message-preview</div></div>';
                            document.querySelector('#mud-sms-msgs').innerHTML = '<div class="mud-bub">' + 'LongMessage'.repeat(100) + '</div>';
                        }''', [common, sms, lang])
                        page.add_style_tag(content=css)
                        result = page.evaluate('''() => {
                            const root=document.querySelector('.mud-sms'), box=root.getBoundingClientRect();
                            const overflow=[...root.querySelectorAll('input,textarea,button,.mud-bub,.mud-chat,.mud-thread')]
                                .filter(e=>{const r=e.getBoundingClientRect();return r.right>box.right+1||r.left<box.left-1;})
                                .map(e=>e.id||e.className);
                            return {overflow, width:document.documentElement.scrollWidth,
                                chinese:/[\u3400-\u9fff]/.test(root.innerText),
                                background:getComputedStyle(root.querySelector('.mud-chat')).backgroundColor,
                                color:getComputedStyle(root.querySelector('input')).color};
                        }''')
                        label = (width, theme, dark, lang)
                        assert not result['overflow'], (label, result)
                        assert result['width'] <= width, (label, result)
                        assert lang == 'zh' or not result['chinese'], (label, 'untranslated', page.inner_text('.mud-sms'))
                        assert result['background'] == ('rgb(32, 34, 38)' if dark else 'rgb(255, 255, 255)'), (label, result)
                        assert result['color'] == ('rgb(238, 238, 238)' if dark else 'rgb(34, 34, 34)'), (label, result)
                        checked += 1
                        page.close()
        browser.close()
    print(f'SMS layout: {checked} viewport/theme/locale cases passed')


if __name__ == '__main__':
    main()
