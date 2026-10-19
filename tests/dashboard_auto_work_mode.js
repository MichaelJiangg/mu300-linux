// Execute the actual LuCI view and translations without RPC/modem access.
const fs = require('fs'), path = require('path'), assert = require('assert');
const repo = path.resolve(process.argv[2] || '.');
const family = fs.existsSync(path.join(repo,'openwrt/luci-app-t551m')) ? 't551m' : 'mu300';
const base = path.join(repo,'openwrt/luci-app-'+family,'htdocs/luci-static/resources');
const L = {env:{lang:'zh'}};
const common = new Function('rpc','baseclass','L',fs.readFileSync(path.join(base,'mu300/common.js'),'utf8'))(
    {declare:()=>()=>Promise.resolve({})},{extend:x=>x},L);
const source = fs.readFileSync(path.join(base,'view/mu300/settings.js'),'utf8');
(async function() {
    for (const lang of ['zh','en','tr']) for (const def of ['134','152'])
        for (const value of [undefined,'default','134','152','invalid']) {
            L.env.lang=lang;
            const options=[]; let loaded=false;
            const uci={load:()=>{loaded=true;return Promise.resolve();}, get:(config,section,key)=>{
                assert(loaded);return key==='auto_work_mode_default'?def:key==='auto_work_mode'?value:undefined;
            }};
            const section={option:(type,name,label)=>{
                const option={name,label,values:[],value:(v,text)=>option.values.push([v,text]),depends:()=>{}};
                options.push(option);return option;
            }};
            const form={Map:function(){this.section=()=>section;this.render=()=>options;}};
            const view=new Function('form','view','M','uci','R',source)(form,{extend:x=>x},
                {translate:common.translate,localizeMenu:()=>{}},uci,{seconds:()=>2});
            await view.load();await view.render();
            const option=options.find(o=>o.name==='auto_work_mode');
            assert(option);assert.deepEqual(option.values.map(v=>v[0]),['default','134','152']);
            assert(option.values[0][1].includes(def));
            assert.equal(option.cfgvalue('main'),['134','152'].includes(value)?value:'default');
            assert.equal(option.default,'default');assert.equal(option.rmempty,false);
            if(lang!=='zh')assert(!/[\u3400-\u9fff]/.test(option.label+option.description+option.values[0][1]));
        }
    console.log('PASS: automatic-mode defaults, overrides and three-language view ('+family+')');
})().catch(e=>{console.error(e);process.exit(1);});
