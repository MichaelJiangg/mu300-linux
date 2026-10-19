'use strict';
'require baseclass';
'require rpc';
'require poll';
'require mu300.common as M';

const get = rpc.declare({object:'unisoc-cpu-cores', method:'get', expect:{}});
const apply = rpc.declare({object:'unisoc-cpu-cores', method:'apply', params:['cores','persist','reset'], expect:{}});
const errors = {
    cpu_cores_invalid:'CPU 核心配置无效', cpu_cores_topology:'CPU 核心列表已变化，请重新载入',
    cpu_cores_fixed:'此核心由内核管理，不能关闭', cpu_cores_save:'无法保存核心设置',
    cpu_cores_write:'内核未接受核心开关设置', cpu_cores_busy:'核心设置正忙，请稍后重试'
};
function node(tag, cls, text) {
    const el=document.createElement(tag);
    if (cls) el.className=cls;
    if (text != null) el.textContent=M.translate(text);
    return el;
}
function message(error) { return M.translate(errors[error] || '无法读取 CPU 核心状态'); }

return baseclass.extend({
    render: function() {
        const card=node('section','mud-card mud-cpu-section mud-cpu-cores');
        card.dataset.scope='cores';
        card.append(node('style',null,`
.mud-cpu-cores .mud-core-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}
.mud-cpu-cores .mud-core{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px;border:1px solid var(--hairline,#ddd);border-radius:10px;background:var(--surface-sunken,var(--surface,#fff));color:var(--text,#222);cursor:pointer;margin:0}
.mud-cpu-cores .mud-core-copy{display:flex;flex-direction:column;gap:5px;font-size:.85rem}
.mud-cpu-cores .mud-core-copy small{font-size:.7rem;color:var(--text-muted,#777)}
.mud-cpu-cores input[type=checkbox]{width:17px;height:17px;min-height:0;flex-shrink:0;margin:0;accent-color:var(--brand,#2f7bf6)}
.mud-cpu-cores .mud-core:has(input:disabled){cursor:default}
.mud-cpu-cores .mud-core-error{color:var(--danger,#df596a)}
.mud-cpu-cores .mud-core-status{margin-top:14px;font-size:.75rem;line-height:1.65;overflow-wrap:anywhere}
`));
        const heading=node('div','mud-cpu-heading');
        heading.append(node('h3',null,'CPU 核心开关'),node('span','mud-cpu-badge','即时生效'));
        const note=node('p','cpu-note','按内核能力逐核开启或关闭。CPU0 保持在线；关闭核心会降低并行处理能力，是否省电取决于实际负载。');
        const grid=node('div','mud-core-grid'), footer=node('div','mud-cpu-actions');
        const persist=node('input');persist.type='checkbox';persist.dataset.corePersist='';
        const label=node('label','mud-cpu-persist');
        const copy=node('span');copy.append(node('span',null,'开机自动应用'),node('small','mud-note','仅保存核心开关；不改变调频、调压和温控配置。'));
        label.append(persist,copy);
        const save=node('button','mud-btn on','应用核心设置'), reset=node('button','mud-btn','恢复核心初始状态');
        save.type=reset.type='button';save.disabled=reset.disabled=true;
        footer.append(label,save,reset);
        const status=node('div','mud-core-status','正在读取核心状态…');status.setAttribute('role','status');
        card.append(heading,note,grid,footer,status);
        let current=null, inputs=[], busy=false, dirty=false, attached=false;
        function report(text,error) {status.textContent=text;status.classList.toggle('mud-core-error',!!error);}
        function paint(state) {
            current=state;grid.replaceChildren();inputs=[];
            for(const c of state.cores || []) {
                const row=node('label','mud-core'), text=node('span','mud-core-copy');
                const title=node('strong',null,'CPU '+c.id), live=node('small',null,c.online?'在线':'离线');live.dataset.coreLive=String(c.id);
                text.append(title,live);
                const input=node('input');input.type='checkbox';input.checked=c.online;input.disabled=!c.writable;input.dataset.core=String(c.id);
                input.setAttribute('aria-label','CPU '+c.id);input.title=c.writable?'':M.translate(c.id===0?'CPU0 保持在线':'此核心由内核管理，不能关闭');
                input.onchange=()=>{dirty=true;};
                row.append(text,input);grid.append(row);inputs.push({c,input});
            }
            persist.checked=!!state.persistent;dirty=false;
            save.disabled=reset.disabled=!(state.cores || []).some(c=>c.writable);
            report(state.boot_error?message(state.boot_error):'',!!state.boot_error);
        }
        persist.onchange=()=>{dirty=true;};
        async function submit(isReset) {
            if(busy || !current) return;
            busy=true;card.querySelectorAll('button,input').forEach(e=>e.disabled=true);
            try {
                const result=await apply(inputs.map(({c,input})=>({id:c.id,online:input.checked})),isReset?false:persist.checked,isReset);
                if(!result.ok) {
                    let text=message(result.error);
                    if(result.rollback===false) text+=' · '+M.translate('回滚未完成，请检查实际核心状态');
                    throw new Error(text);
                }
                paint(result);
                report(M.translate('核心设置已应用；调频与温控页面将在下次打开时刷新。'));
            } catch(e) { report(e.message,true); }
            finally {
                busy=false;persist.disabled=false;
                inputs.forEach(({c,input})=>input.disabled=!c.writable);
                save.disabled=reset.disabled=!inputs.some(({c})=>c.writable);
            }
        }
        save.onclick=()=>submit(false);reset.onclick=()=>submit(true);
        get().then(s=>{if(!s.ok) throw new Error(message(s.error));paint(s);}).catch(e=>report(e.message,true));
        // Reuse LuCI polling only while this page is visible; never overwrite edits.
        function refresh() {
            if(!card.isConnected) {
                if(attached && poll.remove) poll.remove(refresh);
                return Promise.resolve();
            }
            attached=true;
            if(document.hidden || busy) return Promise.resolve();
            return get().then(s=>{
                if(!s.ok) throw new Error(message(s.error));
                if(!dirty) paint(s);
                else (s.cores || []).forEach(c=>{
                    const el=grid.querySelector('[data-core-live="'+c.id+'"]');
                    if(el) el.textContent=M.translate(c.online?'在线':'离线');
                });
            }).catch(e=>report(e.message,true));
        }
        poll.add(refresh,2);
        return card;
    }
});
