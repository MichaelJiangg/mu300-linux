"""Render MU300 cipher controls with the actual pinned LuCI Select, offline."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

TOP=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wireless',type=Path,required=True)
    parser.add_argument('--ui',type=Path,required=True)
    args=parser.parse_args()
    text=args.wireless.read_text(encoding='utf-8')
    start=text.rfind('o=',0,text.index("'cipher',"));end=text.index('const crypto_modes',start)
    controls=text[start:end]
    native=args.ui.read_text(encoding='utf-8');native=native[native.index('const UISelect='):native.index('const UIDropdown=')]
    feature=(TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/wifi-ciphers.js').read_text(encoding='utf-8')
    with sync_playwright() as p:
        chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        browser=p.chromium.launch(**({'executable_path':str(chrome)} if chrome.exists() else {}))
        page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        result=page.evaluate('''async ([source,native,feature])=>{
            const E=(tag,attrs,children=[])=>{const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{}))if(v!=null)e.setAttribute(k,v);for(const c of children)e.append(c);return e;};
            const L={env:{lang:'en'},isObject:x=>x&&typeof x==='object'};
            const base={extend(methods){function Widget(...args){this.__init__(...args)}Widget.prototype={setUpdateEvents(){},setChangeEvents(){},...methods};return Widget;}};
            const Select=new Function('UIElement','L','E','dom','_',native+';return UISelect;')(base,L,E,{bindClassInstance(){}},x=>x);
            const moduleBase={extend(methods){function Module(){}Object.assign(Module.prototype,methods);return Module;}};
            const exported=new Function('fs','L','_','baseclass',feature)({exec_direct:()=>Promise.reject(new Error('unavailable'))},L,x=>x,moduleBase);
            if(typeof exported!=='function')throw new Error('LuCI module must export a constructor');
            const support=new exported();
            const factory=new Function('ss','form','_','uci','support','caps','let o;'+source+';support.apply(o,caps);return o;');
            function make(suites,saved) {const option={keylist:[],vallist:[],depends(){},value(v,label){this.keylist.push(v);this.vallist.push(label)}};return factory({children:[{option:'encryption',write(){}}],taboption(){return option}},{ListValue:{}},x=>x,{get(){return saved}},support,{suites});}
            const checks=[];
            for(const language of ['zh-cn','en','tr']){
                L.env.lang=language;
                for(const cipher of ['gcmp','gcmp256','ccmp256']){
                    const control=make(['00-0f-ac:4'],'sae+'+cipher);
                    const labels=()=>Object.fromEntries(control.keylist.map((k,i)=>[k,control.vallist[i]]));
                    const old=new Select(cipher,labels(),{sort:control.keylist.slice()});document.body.append(old.render());
                    const value=control.cfgvalue('id');const current=new Select(value,labels(),{sort:control.keylist});document.body.append(current.render());
                    checks.push({before:old.getValue(),after:current.getValue(),expected:cipher,valid:control.validate('id',current.getValue())});
                }
            }
            const another=make(['00-0f-ac:4','00-0f-ac:8'],'sae+gcmp');
            return {checks,other:another.validate('id',another.cfgvalue('id')),unknown:await support.load('radio0')};
        }''',[controls,native,feature])
        for check in result['checks']:
            assert check['before']=='auto' and check['after']==check['expected'],check
            assert isinstance(check['valid'],str),check
        assert result['other'] is True and result['unknown']=={},result
        assert not errors,errors
        browser.close()
        print('PASS: native LuCI select, 3 languages, saved invalid ciphers, independent PHY and failed capability read')


if __name__=='__main__':main()
