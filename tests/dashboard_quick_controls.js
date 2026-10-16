'use strict';
const assert = require('assert'), fs = require('fs'), path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/home.js'), 'utf8');
const tick = async () => { for (let i=0; i<20; i++) await Promise.resolve(); };
function fixture(on) {
    const buttons = {}, requests = [], dialogs = [];
    let decide, complete;
    const root = {isConnected:true, querySelector(id) {
        return buttons[id] || (buttons[id] = {disabled:false, addEventListener(){}});
    }};
    const M = {
        confirmBox(title,body,options) { dialogs.push({title,body,options}); return new Promise(resolve => { decide=resolve; }); },
        callAct(op,arg) { requests.push([op,arg]); return new Promise(resolve => { complete=resolve; }); },
        busy(btn,on) { btn.busy=on; }, toast(){}
    };
    const view = new Function('view','uci','R','M','L',source)(
        {extend:o=>o},{},{},M,{resolveDefault:p=>p.catch(()=>undefined)});
    view.refreshLock = () => {};
    view.wire(root);
    view.lastInfo = {wan:{up:on},wifi:{available:1,up:on,pending:false}};
    view.lastCell = {cfun:on?1:0};
    return {view,root,buttons,requests,dialogs,decide:v=>decide(v),complete:()=>complete({ok:1})};
}
(async()=>{
    const cases = [
        ['data',true,'data','down'], ['data',false,'data','up'],
        ['radio',true,'radio','off'], ['radio',false,'radio','on'],
        ['wifi',true,'wifi','off'], ['wifi',false,'wifi','on'],
        ['modem',true,'modem-reset',null], ['reboot',true,'reboot',null], ['android',true,'os','android']
    ];
    for (const [id,on,op,arg] of cases) {
        for (const decision of ['cancel','confirm','unload','detach']) {
            const f=fixture(on), button=f.buttons['#mud-btn-'+id];
            button.onclick();
            assert.equal(f.dialogs.length,1,id);
            assert.equal(f.requests.length,0,id+' executed before confirmation');
            button.onclick(); f.buttons['#mud-btn-reboot'].onclick();
            assert.equal(f.dialogs.length,1,'duplicate confirmation');
            if (decision==='unload') f.view.unload();
            if (decision==='detach') f.root.isConnected=false;
            // Even if polling changes state, send only the explicit confirmed target.
            f.view.lastInfo.wan.up=!on; f.view.lastCell.cfun=on?0:1;
            f.view.lastInfo.wifi.up=!on;
            f.decide(decision!=='cancel'); await tick();
            if (decision==='confirm') {
                assert.deepEqual(f.requests,[[op,arg]],id);
                button.onclick(); assert.equal(f.requests.length,1,'duplicate in-flight request');
                assert(button.busy);
                f.complete(); await tick();
                assert(!button.busy && !button.disabled,id+' left busy');
            } else assert.equal(f.requests.length,0,id+' must not execute after '+decision);
            assert(!f.view._quickPending,id+' left confirmation locked');
        }
    }
    for(const state of ['pending','unavailable','busy']) {
        const f=fixture(true);
        if(state==='pending')f.view.lastInfo.wifi.pending=true;
        if(state==='unavailable')f.view.lastInfo.wifi.available=0;
        if(state==='busy')f.view._wifiBusy=true;
        f.buttons['#mud-btn-wifi'].onclick(); assert.equal(f.dialogs.length,0,state);
    }
    console.log('PASS: all six quick controls confirmed; on/off, cancellation, leaving view, duplicate clicks, busy cleanup and fixed targets');
})().catch(e=>{console.error(e);process.exitCode=1;});
