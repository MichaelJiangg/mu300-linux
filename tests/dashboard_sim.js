'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert');
const dir=path.resolve(__dirname,'../openwrt/luci-app-mu300/htdocs/luci-static/resources');
const store=new Map(), session={getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)};
let called=[];
const common=new Function('rpc','baseclass','L','document','navigator','sessionStorage',fs.readFileSync(dir+'/mu300/common.js','utf8'))(
    {declare:o=>(...args)=>{called.push([o.method,args]); return Promise.resolve({});}},
    {extend:o=>o},{env:{lang:'en'}},{},{},session);
assert.equal(common.selectedSlot(),'0');
common.selectViewedSlot(1); assert.equal(common.selectedSlot(),'1');
assert.equal(common.selectViewedSlot(2),false); assert.equal(common.selectedSlot(),'1');
common.callAt('AT'); common.selectViewedSlot(0);
assert.deepEqual(called[0],['at',['AT','1']]);

function element(tag) {return {tag,children:[],style:{},isConnected:true,append(...n){this.children.push(...n);}};}
function find(root,tag){return root.tag===tag?root:root.children.map(n=>find(n,tag)).find(Boolean);}
const tick=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
(async()=>{
    for(const outcome of ['cancel','error','done']) {
        common.selectViewedSlot('0'); let requests=0;
        const M={injectCss(){},localizeMenu(){},translate:s=>s,selectViewedSlot:common.selectViewedSlot,
            confirmBox:()=>Promise.resolve(outcome!=='cancel'),busy:(b,v)=>b.busy=v,toast:()=>({close(){}})};
        const rpc={declare:o=>()=>{
            if(o.method==='data_sim_set'){requests++;return Promise.resolve({ok:1,id:'abcdefghij'});}
            if(o.method==='data_sim_status')return Promise.resolve({id:'abcdefghij',state:outcome,ok:outcome==='done',error:'rejected'});
            return Promise.resolve({ok:1,saved_sim:1,actual_sim:1,data_connected:false});
        }};
        const view=new Function('view','rpc','poll','M','document','SimRadio',fs.readFileSync(dir+'/view/mu300/sim.js','utf8'))(
            {extend:o=>o},rpc,{add(){},remove(){}},M,{createElement:element},{attach:()=>({refresh:()=>Promise.resolve(),dispose(){}})});
        const root=view.render([{slots:2},{ok:1,ready:true,saved_sim:0,actual_sim:0}]);
        const section=find(root,'section'), row=find(section,'select');
        assert(root.className.includes('mud-sim-page'));
        assert(find(section,'h3'), 'heading belongs inside the card');
        assert.equal(find(section,'label').htmlFor,row.id);
        assert.equal(find(section,'button').type,'button');
        assert(find(root,'style').textContent.includes('@media(max-width:480px)'));
        find(root,'select').value='1';find(root,'button').onclick();await tick();
        assert.equal(common.selectedSlot(),outcome==='done'?'1':'0',outcome);
        assert.equal(requests,outcome==='cancel'?0:1);
        assert(!view.busy && !find(root,'button').busy,outcome+' left loading active');
        view.unload();
    }
    {
        common.selectViewedSlot('0');
        const state={ok:1,native:true,hot:0,ready:false,saved_sim:0,actual_sim:0,data_connected:true};
        const requests=[];
        const M={injectCss(){},localizeMenu(){},translate:s=>s,
            selectViewedSlot:common.selectViewedSlot,
            confirmBox:()=>Promise.resolve(true),busy:(b,v)=>b.busy=v,toast:()=>({close(){}})};
        const rpc={declare:o=>(target)=>{
            if(o.method==='data_sim_get')return Promise.resolve({...state});
            if(o.method==='data_sim_set') {
                requests.push(target);
                if(target.startsWith('u30-hot-'))state.hot=Number(target.slice(-1));
                else if(target.startsWith('u30-default-'))state.saved_sim=Number(target.slice(-1));
                else {state.actual_sim=Number(target);state.saved_sim=Number(target);}
                return Promise.resolve({ok:1,id:'abcdefghij'});
            }
            return Promise.resolve({id:'abcdefghij',state:'done',ok:1});
        }};
        const view=new Function('view','rpc','poll','M','document','SimRadio',fs.readFileSync(dir+'/view/mu300/sim.js','utf8'))(
            {extend:o=>o},rpc,{add(){},remove(){}},M,{createElement:element},{attach:()=>({refresh:()=>Promise.resolve(),dispose(){}})});
        const root=view.render([{slots:2},{...state}]);
        function all(n,tag){return (n.tag===tag?[n]:[]).concat(...n.children.map(c=>all(c,tag)));}
        const [switchButton,saveButton]=all(root,'button');
        const select=find(root,'select'), hot=find(root,'input');
        assert(switchButton.disabled,'cold SIM1 boot must not offer an unprepared live switch');
        assert(!select.disabled,'next-boot selection must remain available');
        select.value='1';saveButton.onclick();await tick();
        assert.deepEqual(requests,['u30-default-1']);
        assert.equal(state.actual_sim,0,'saving boot preference must not change current radio');
        assert.equal(common.selectedSlot(),'0','configuration does not change viewed slot');
        hot.checked=true;hot.onchange();await tick();
        assert.equal(requests[1],'u30-hot-1');
        assert(switchButton.disabled,'enabling policy alone is not broker initialization');
        state.ready=true;await view.refresh();
        assert(!switchButton.disabled,'ready state must enable the live control without a page reload');
        select.value='1';switchButton.onclick();await tick();
        assert.equal(requests[2],'1');
        assert.equal(common.selectedSlot(),'1');
        view.unload();
    }
    console.log('SIM UI: scoped RPC and native U30 boot/live controls pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
