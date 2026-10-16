from pathlib import Path
from playwright.sync_api import sync_playwright
import re

top=Path(__file__).resolve().parents[1]
js=top/'openwrt/luci-app-mu300/htdocs/luci-static/resources'
common=(js/'mu300/common.js').read_text(encoding='utf-8')
cpu=(js/'view/mu300/cpu.js').read_text(encoding='utf-8')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='C:/Users/kano/AppData/Local/ms-playwright/chromium-1024/chrome-win/chrome.exe')
    for theme in ('aurora','bootstrap'):
        for dark in (False,True):
            for lang in ('zh-cn','en','tr'):
                for width in (360,1280):
                    page=browser.new_page(viewport={'width':width,'height':900})
                    errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('http://mu300.test/**',lambda r:r.fulfill(body='<html><body></body></html>',content_type='text/html'))
                    page.goto('http://mu300.test/')
                    bg,surface,text,muted,border=('#15171b','#202329','#eee','#a5a9b0','#383c44') if dark else ('#f4f5f7','#fff','#202329','#626874','#dce0e6')
                    tokens={'surface':surface,'surface-sunken':bg,'text':text,'text-muted':muted,'hairline':border,'brand':'#447bee'} if theme=='aurora' else {'background-color-high':surface,'background-color-low':bg,'text-color-high':text,'text-color-medium':muted,'text-color-low':muted,'border-color-low':border,'primary-color-high':'#447bee'}
                    page.add_style_tag(content='html{'+''.join(f'--{k}:{v};' for k,v in tokens.items())+'}body{margin:16px;background:'+bg+';color:'+text+';font-family:Arial,sans-serif}*{box-sizing:border-box}')
                    page.evaluate('''([common,cpu,lang])=>{
                        window.L={env:{lang}}; window.requests=[];
                        window.data={ok:1,persist:false,policies:[0,4,7].map((id,i)=>({id:'policy'+id,cpus:['0 1 2 3','4 5 6','7'][i],driver:'sprd-cpufreq-v2',governors:['schedutil','performance'],governor:'schedutil',frequencies:[408000,1000000,1800000],min:408000,max:1800000,hardware_min:408000,hardware_max:1800000,current:1000000,writable:true})),zones:[{name:'soc-thmzone',id:'thermal_zone19',temp:42000,minimum:40000,maximum:100000,step:1000,mode:'enabled',policy:'step_wise',trips:[{id:0,type:'passive',temp:70000,hysteresis:1000,writable:true,throttles_cpu:false},{id:1,type:'passive',temp:85000,hysteresis:1000,writable:true,throttles_cpu:true},{id:2,type:'critical',temp:110000,hysteresis:2000,writable:false}],cooling:[{id:'cdev0',type:'cpufreq-cpu0',state:0,max_state:9}]},{name:'lit0-thmzone',id:'thermal_zone7',temp:40000,trips:[],cooling:[]}],voltage:{supported:false}};
                        const rpc={declare:o=>(payload)=>{if(o.method==='cpu_apply'){requests.push(JSON.parse(payload));}return Promise.resolve(data);}};
                        const M=new Function('rpc','baseclass','L',common)(rpc,{extend:o=>o},L);
                        window.view=new Function('view','rpc','poll','M',cpu)({extend:o=>o},rpc,{add(){},remove(){}},M);
                        document.body.append(view.render(data));
                    }''',[common,cpu,lang])
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(theme,dark,lang,width,'overflow')
                    if lang!='zh-cn':
                        assert not re.search(r'[\u4e00-\u9fff]',page.locator('.mud-cpu').inner_text()),page.locator('.mud-cpu').inner_text()
                    assert page.locator('.mud-cpu-section').evaluate_all("es=>es.map(e=>e.dataset.scope)")==['frequency','voltage','thermal']
                    assert page.locator('.mud-cpu-thermal-trips input').count()==2
                    thermal=page.locator('[data-scope="thermal"]')
                    frequency=page.locator('[data-scope="frequency"]')
                    freqmax=frequency.locator('.mud-cpu-range select').nth(1)
                    freqmax.select_option('1000000')
                    page.locator('.mud-cpu-thermal-trips input').first.fill('69')
                    page.evaluate('view.refresh()')
                    assert page.locator('.mud-cpu-thermal-trips input').first.input_value()=='69'
                    page.evaluate('view.persist.checked=true;view.thermalPersist.checked=true')
                    # Thermal cancellation cannot write. Applying it preserves frequency edits.
                    thermal.locator('.mud-cpu-actions .mud-btn.on').click()
                    page.keyboard.press('Escape')
                    assert page.evaluate('requests.length')==0
                    thermal.locator('.mud-cpu-actions .mud-btn.on').click()
                    if lang!='zh-cn': assert not re.search(r'[\u4e00-\u9fff]',page.locator('.mud-dlg').inner_text())
                    page.locator('.mud-dlg [data-r="1"]').click()
                    page.wait_for_function('requests.length===1 && !view.busy')
                    sent=page.evaluate('requests[0]')
                    assert sent['thermal'][0]=={'zone':'soc-thmzone','trip':0,'temp':69000}
                    assert sent['scope']=='thermal' and sent['persist'] and 'changes' not in sent
                    assert freqmax.input_value()=='1000000'
                    assert page.evaluate('view.persist.checked')
                    # Invalid unfinished thermal input must not block a frequency save.
                    page.locator('.mud-cpu-thermal-trips input').first.fill('20')
                    page.evaluate('view.thermalPersist.checked=true')
                    frequency.locator('.mud-cpu-actions .mud-btn.on').click()
                    page.locator('.mud-dlg [data-r="1"]').click()
                    page.wait_for_function('requests.length===2 && !view.busy')
                    sent=page.evaluate('requests[1]')
                    assert sent['scope']=='frequency' and 'thermal' not in sent and sent['persist']
                    assert sent['changes'][0]['max']==1000000
                    assert page.locator('.mud-cpu-thermal-trips input').first.input_value()=='20'
                    assert page.evaluate('view.thermalPersist.checked')
                    # Each reset is scoped; even the unsubmitted other draft survives.
                    for scope,section in [('frequency',frequency),('thermal',thermal)]:
                        before=page.evaluate('requests.length')
                        section.locator('.mud-cpu-actions .mud-btn:not(.on)').click()
                        if lang!='zh-cn': assert not re.search(r'[\u4e00-\u9fff]',page.locator('.mud-dlg').inner_text())
                        page.locator('.mud-dlg [data-r="1"]').click()
                        page.wait_for_function('n=>requests.length===n+1 && !view.busy',arg=before)
                        assert page.evaluate('requests[requests.length-1]')=={'scope':scope,'reset':True}
                        if scope=='frequency': assert page.locator('.mud-cpu-thermal-trips input').first.input_value()=='20'
                    assert not errors,errors
                    if theme=='aurora' and lang=='zh-cn':page.screenshot(path=str(top/f'work/cpu-thermal-{width}-{dark}.png'),full_page=True)
                    page.close()
    browser.close()
print('PASS 24 CPU layouts: frequency/voltage/thermal order, independent apply/reset/auto-apply, preserved other drafts, zh/en/tr, Aurora/Bootstrap light/dark, mobile/desktop')
