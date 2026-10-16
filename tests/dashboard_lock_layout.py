"""Offline regression: lock refresh indicators must never shift content.

Run: python tests/dashboard_lock_layout.py --browser PATH_TO_CHROME
"""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

RES = Path(__file__).resolve().parents[1] / 'openwrt/luci-app-mu300/htdocs/luci-static/resources'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser')
    args = parser.parse_args()
    common = (RES / 'mu300/common.js').read_text(encoding='utf-8')
    locks = (RES / 'view/mu300/locks.js').read_text(encoding='utf-8')
    cases = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({'executable_path': args.browser} if args.browser else {}))
        for width in (320, 390, 1280):
            for theme in ('bootstrap', 'aurora'):
                for dark in (False, True):
                    for lang in ('zh', 'en', 'tr'):
                        page = browser.new_page(viewport={'width': width, 'height': 900})
                        page.route('**/*', lambda route: route.abort())
                        page.set_content('<html><head></head><body><main id="app"></main></body></html>')
                        bg, fg = ('#202226', '#eeeeee') if dark else ('#ffffff', '#222222')
                        variables = (f'--surface:{bg};--text:{fg};--hairline:#777;--brand:#467bef;' if theme == 'aurora' else
                                     f'--background-color-high:{bg};--background-color-low:{bg};--text-color-high:{fg};--border-color-low:#777;--primary-color-high:#467bef;')
                        page.add_style_tag(content=f'html{{{variables}}}body{{margin:0;padding:12px;font-family:sans-serif}}main{{max-width:1050px;margin:auto;min-width:0}}')
                        page.evaluate('''([common, locks, lang]) => {
                            const L={env:{lang}}, base={extend:x=>x};
                            const M=new Function('rpc','baseclass','L',common)({declare:()=>()=>{}},base,L);
                            M.watchSms=()=>{};
                            window.view=new Function('view','M',locks)(base,M);
                            view.wire=function(root){this.Q=id=>root.querySelector('#mud-'+id);};
                            document.querySelector('#app').appendChild(view.render());
                        }''', [common, locks, lang])
                        sizes = []
                        for pending, failed in ((False, False), (True, False), (False, False), (False, True)):
                            sizes.append(page.evaluate('''([pending,failed]) => {
                                ['serving','lock','neighbor'].forEach(part=>view.loading(part,pending,failed));
                                return [...document.querySelectorAll('.mud-lock-heading,.mud-lock-progress,.mud-sec,.mud-hero,.mud-ctl,.mud-scroll')]
                                    .map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height];});
                            }''', [pending, failed]))
                        assert all(s == sizes[0] for s in sizes), (width, theme, dark, lang, 'layout shift')
                        gap = page.evaluate('''() => {
                            const label=document.querySelector('.mud-hero .mud-heading-label').getBoundingClientRect();
                            const progress=document.querySelector('#mud-serving-progress').getBoundingClientRect();
                            return progress.left-label.right;
                        }''')
                        assert abs(gap - 8) < 1, (width, theme, dark, lang, 'not next to serving label', gap)
                        assert page.evaluate("[...document.querySelectorAll('.mud-lock-progress')].every(e=>e.parentElement.classList.contains('mud-lock-heading'))")
                        assert page.evaluate("[...document.querySelectorAll('.mud-lock-progress')].every(e=>getComputedStyle(e).whiteSpace==='nowrap')")
                        page.close()
                        cases += 1
        browser.close()
    print(f'Lock headings: {cases} viewport/theme/locale cases; idle/loading/error geometry identical')


if __name__ == '__main__':
    main()
