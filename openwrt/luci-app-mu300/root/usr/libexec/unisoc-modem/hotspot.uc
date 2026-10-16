// Single source of AP selection for dashboard display and quick actions.
// Runtime data is used only for matching/status, never as a source of secrets.
export function status(c, runtime, selected, device) {
    let aps=[], matches=[];
    c.foreach('wireless','wifi-iface',s=>{ if(s.mode=='ap') push(aps,s); });
    for(let ap in aps) {
        let r=runtime?.[ap.device];
        let found=ap.ifname==device;
        for(let i in r?.interfaces ?? [])
            if(i.section==ap['.name'] && i.ifname==device) found=true;
        if(found) push(matches,ap);
    }
    let ap;
    if(selected) {
        for(let candidate in aps) if(candidate['.name']==selected) ap=candidate;
        if(!ap) return {available:false,up:false,error:'热点配置节不存在或不是 AP'};
    } else if(length(matches)==1) ap=matches[0];
    else if(length(aps)==1) ap=aps[0];
    else return {available:false,up:false,error:length(aps)?'存在多个热点，请在适配设置选择目标 AP':'没有配置热点'};
    let name=ap['.name'], radio=ap.device;
    if(!match(name,/^[a-zA-Z0-9_]+$/) || !radio || c.get('wireless',radio)!='wifi-device')
        return {available:false,up:false,error:'热点所属无线电无效'};
    let rs=runtime?.[radio], iface=ap.ifname, present=false;
    for(let i in rs?.interfaces ?? []) if(i.section==name) {iface=i.ifname || iface;present=true;}
    if(iface && !match(iface,/^[a-zA-Z0-9_.:-]{1,15}$/)) iface=null;
    let enabled=ap.disabled!='1' && c.get('wireless',radio,'disabled')!='1';
    return {available:true,section:name,radio,device:iface,enabled,
        up:enabled && rs?.up==true && present,pending:rs?.pending==true,
        ssid:ap.ssid,enc:ap.encryption || 'none',hidden:ap.hidden=='1'?1:0,
        channel:c.get('wireless',radio,'channel'),
        band:c.get('wireless',radio,'band') || c.get('wireless',radio,'hwmode'),
        htmode:c.get('wireless',radio,'htmode'),country:c.get('wireless',radio,'country')};
};

export function set(c,on,runtime,selected,device,reload) {
    if(type(on)!='bool') return {ok:0,error:'热点开关参数无效'};
    let ap=status(c,runtime,selected,device);
    if(!ap.available) return {ok:0,error:ap.error};
    if(ap.pending) return {ok:0,error:'热点正在应用配置，请稍后重试'};
    // Never commit or discard unrelated edits made in LuCI's wireless page.
    if(length(c.changes('wireless') ?? {})) return {ok:0,error:'无线配置有未应用更改，请先保存或撤销'};
    if(ap.enabled==on && ap.up==on && (on || c.get('wireless',ap.section,'disabled')=='1'))
        return {ok:1,op:'wifi '+(on?'on':'off'),unchanged:1};
    let disabled=c.get('wireless',ap.radio,'disabled')=='1', conflict=false;
    if(on && disabled) c.foreach('wireless','wifi-iface',s=>{
        if(s['.name']!=ap.section && s.device==ap.radio && s.disabled!='1') conflict=true;
    });
    if(conflict) return {ok:0,error:'启用此无线电会影响其他接口，请在无线页面处理'};
    if(!c.set('wireless',ap.section,'disabled',on?'0':'1') ||
        (on && disabled && !c.set('wireless',ap.radio,'disabled','0'))) {
        c.revert('wireless'); return {ok:0,error:'热点配置写入失败'};
    }
    if(!c.commit('wireless')) {
        c.revert('wireless'); return {ok:0,error:'热点配置保存失败'};
    }
    if(!reload()) return {ok:0,saved:1,error:'热点配置已保存，但应用失败，请重试'};
    // netifd applies asynchronously: don't claim that association already works.
    return {ok:1,pending:1,op:'wifi '+(on?'on':'off')};
};
