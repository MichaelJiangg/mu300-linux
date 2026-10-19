'use strict';
'require baseclass';
'require rpc';
'require mu300.common as M';

// Change only this UCI option. Never run uci.apply() or restart services here;
// the lock page owns confirmation, selected-SIM checks and the existing job.
const get = rpc.declare({object:'uci',method:'get',params:['config','section'],expect:{values:{}},reject:true});
const set = rpc.declare({object:'uci',method:'set',params:['config','section','values'],reject:true});
const commit = rpc.declare({object:'uci',method:'commit',params:['config'],reject:true});

function node(tag,cls,text) {
    const el=document.createElement(tag);
    if(cls) el.className=cls;
    if(text!=null) el.textContent=M.translate(text);
    return el;
}
return baseclass.extend({
    attach: function(root,request) {
        root.hidden=true;
        root.className='mud-auto-mode';
        const style=node('style',null,`
.mud-auto-mode{margin-top:14px;max-width:520px;min-width:0}
.mud-auto-mode[hidden]{display:none!important}
.mud-auto-mode label{display:flex;flex-direction:column;gap:7px;margin:0;min-width:0;color:var(--text,#222);font-size:.82rem}
.mud-auto-mode .mud-auto-mode-row{display:flex;flex-wrap:wrap;align-items:end;gap:10px;margin:10px 0 7px}
.mud-auto-mode .mud-auto-mode-row label{flex:1;min-width:min(100%,210px)}
.mud-auto-mode select{box-sizing:border-box;width:100%;max-width:100%;min-height:38px;margin:0;padding:8px 10px;border:1px solid var(--hairline,#ddd);border-radius:8px;background:var(--surface,#fff);color:var(--text,#222)}
.mud-auto-mode .mud-auto-mode-row button{min-height:38px;margin:0;white-space:normal}
.mud-auto-mode .mud-auto-mode-error{color:var(--danger,#df596a);overflow-wrap:anywhere}
`);
        const row=node('div','mud-auto-mode-row'), label=node('label');
        const title=node('span',null,'自动模式兼容性'), input=node('select');
        input.id='mud-auto-mode-select';input.disabled=true;
        label.htmlFor=input.id;label.append(title,input);
        const button=node('button','mud-btn','保存并应用');button.type='button';button.disabled=true;
        row.append(label,button);
        const note=node('div','mud-note','此项可能影响双卡延迟和自动选网偏好，例如联通 n78／n1 的驻留选择；实际效果取决于基带和网络，不保证驻留指定频段。延迟高、网络卡顿或驻留不理想时可尝试调整，应用后会重新连接网络。');
        const scope=node('div','mud-note','兼容性选项由两张 SIM 共用，本次应用到当前查看的 SIM；显式 4G／SA／NSA 模式不受影响。');
        const modes=node('div','mud-note','134：5G／4G／3G／2G 自动，可回落 2G；152：5G／4G／3G 自动，不使用 2G。编号表示制式组合，不代表固定的频段优先级。');
        const status=node('div','mud-note');status.setAttribute('role','status');
        root.append(style,row,modes,note,scope,status);
        let loaded=false, busy=false, mode=null;
        function update(current,applying) {
            mode=current;busy=!!applying;
            root.hidden=!current || (current.label!=='auto' && current.label!=='auto-nsa');
            input.disabled=button.disabled=!loaded || busy;
        }
        function reload() {
            if(loaded) return Promise.resolve();
            status.textContent=M.translate('正在读取兼容性设置…');
            return get('unisoc_modem','main').then(values=>{
                const fallback=values.auto_work_mode_default==='152'?'152':'134';
                const labels={
                    '134':M.translate('全制式自动（134，含 2G）'),
                    '152':M.translate('自动选网（152，不含 2G）')
                };
                input.replaceChildren();
                [['default',M.translate('机型默认')+' · '+labels[fallback]],['134',labels['134']],['152',labels['152']]].forEach(([value,text])=>{
                    const option=node('option',null,text);option.value=value;input.append(option);
                });
                input.value=['134','152'].includes(values.auto_work_mode)?values.auto_work_mode:'default';
                loaded=true;status.textContent='';status.classList.remove('mud-auto-mode-error');
                update(mode,busy);
            }).catch(()=>{
                status.textContent=M.translate('无法读取兼容性设置，请刷新页面后重试');
                status.classList.add('mud-auto-mode-error');
            });
        }
        button.onclick=()=>{
            if(!loaded || busy) return;
            const value=input.value;
            if(!['default','134','152'].includes(value)) return;
            // The selection is a draft until the lock page confirms the job.
            request(button,()=>set('unisoc_modem','main',{auto_work_mode:value})
                .then(()=>commit('unisoc_modem'))
                .catch(error=>{
                    const detail=error && error.message ? ': '+error.message : '';
                    throw new Error(M.translate('保存兼容性设置失败，未执行网络模式应用')+detail);
                }));
        };
        reload();
        return {update,reload};
    }
});
