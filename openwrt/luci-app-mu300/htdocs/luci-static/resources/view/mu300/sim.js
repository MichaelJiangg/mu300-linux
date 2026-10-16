'use strict';
'require view';
'require rpc';
'require poll';
'require mu300.common as M';

var get=rpc.declare({object:'mu300dash',method:'data_sim_get',nobatch:true,expect:{'':{}}});
var start=rpc.declare({object:'mu300dash',method:'data_sim_set',params:['target'],nobatch:true,expect:{'':{}}});
var status=rpc.declare({object:'mu300dash',method:'data_sim_status',params:['id'],nobatch:true,expect:{'':{}}});
var errors={dual_sim_unavailable:'当前配置不支持双卡切换',invalid_sim:'SIM 卡槽无效',modem_busy:'另一项模组操作正在执行',sim_read_failed:'无法核验当前上网卡',sim_not_ready:'目标 SIM 尚未就绪',data_disconnect_failed:'旧数据连接未停止，已取消切换',sim_switch_failed_restored:'切换失败，已恢复原上网卡',sim_rollback_failed:'切换失败且恢复不完整，请检查 SIM 和信号',storage_failed:'设置保存失败'};
errors.dual_boot_required='双卡尚未共同初始化，请重启后检查状态';
Object.assign(errors,{"Enable hot switching first": "请先启用双卡热切换", "Persistent dual-SIM brokers unavailable; reboot first": "双卡通道尚未准备完成，请先重启", "Unknown active SIM; reboot first": "当前上网卡状态未知，请重启", "Unexpected radio state; reboot first": "射频状态异常，请先重启", "No card answers in the target SIM position; nothing was changed": "目标卡槽未检测到 SIM，未进行切换", "The target SIM is locked by its PIN; nothing was changed": "目标 SIM 需要 PIN，未进行切换", "Target SIM got no data within the time; previous SIM restored": "目标卡未建立数据连接，已恢复原卡", "Target SIM has no data yet and the previous SIM had none either; staying on the target, boot default unchanged": "两卡均暂无数据连接，保留当前选卡，开机默认卡未更改", "Active SIM has no data; use default for next-boot selection": "当前卡暂无数据连接，可单独保存为下次开机默认卡", "Cannot stop WAN": "无法停止蜂窝连接，已取消切换", "Interrupted switch; reboot first": "上次切卡被中断，请先重启", "Network locks are being applied": "网络锁定正在应用，请稍后再试", "Previous SIM restored but WAN could not be started": "已恢复原卡，但蜂窝连接未能启动", "Resume the modem before switching": "请先恢复基带运行再切卡", "SIM control is busy": "另一项 SIM 设置正在执行", "SIM switched but the boot default could not be saved": "上网卡已切换，但开机默认卡保存失败", "Switch failed; previous SIM restored": "切卡失败，已恢复原卡", "Switch failed; radio state unknown, reboot required": "切卡失败且射频状态未知，需要重启", "Target SIM got no data and the previous one could not be restored; reboot required": "目标卡无数据且原卡恢复失败，需要重启", "Target SIM got no data; previous SIM restored but WAN could not be started": "目标卡无数据，已恢复原卡但蜂窝连接未启动", "The modem is busy; nothing was changed, try again": "基带正忙，未进行切换，请重试", "The target SIM could not be powered; nothing was changed": "目标 SIM 无法上电，未进行切换", "Unknown radio state; reboot first": "射频状态未知，请先重启", "flock is required for SIM control": "缺少 SIM 互斥组件，请更新完整系统"});
function message(s){return M.translate(errors[s]||s);}
function el(tag,text,cls) { var n=document.createElement(tag); if(text!=null)n.textContent=text; if(cls)n.className=cls; return n; }
function card(n) { return n===0||n===1 ? 'SIM '+(n+1) : M.translate('未连接'); }
var CSS = `
.mud-sim-page .mud-sim-panel{padding:20px;min-width:0}
.mud-sim-page .mud-sim-panel h3{margin:0 0 10px;padding:0;border:0;font-size:1rem;font-weight:600;color:var(--text,#222)}
.mud-sim-page .mud-sim-intro{margin:0 0 16px;line-height:1.65}
.mud-sim-page .mud-data-sim{display:grid;gap:10px;margin:0;padding:14px;border:1px solid var(--hairline,var(--border-color,#ddd));border-radius:10px;min-width:0}
.mud-sim-page .mud-data-sim + .mud-data-sim{margin-top:16px}
.mud-sim-page .mud-data-sim-controls{display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px}
.mud-sim-page .mud-data-sim-controls label{flex:1;min-width:110px;font-weight:600;margin:0;color:var(--text,#222)}
.mud-sim-page .mud-data-sim-controls input[type="checkbox"]{width:18px;height:18px;min-height:0;margin:0;flex:none;accent-color:var(--brand,var(--primary,#2f7bf6))}
.mud-sim-page .mud-data-sim-controls select{width:auto;min-width:100px;max-width:100%;margin:0}
.mud-sim-page .mud-data-sim-controls .mud-btn{margin:0;max-width:100%;white-space:normal}
.mud-sim-page .mud-sim-status{display:flex;flex-wrap:wrap;gap:6px 18px;padding:10px 0 0;border-top:1px solid var(--hairline,var(--border-color,#ddd));font-size:.8rem;line-height:1.6;color:var(--text-muted,#777)}
.mud-sim-page .mud-sim-status span{min-width:0;overflow-wrap:anywhere}
.mud-sim-page .mud-note{line-height:1.65;overflow-wrap:anywhere}
.mud-sim-page .mud-data-sim .mud-note{margin:0}
@media(max-width:480px){.mud-sim-page .mud-sim-panel{padding:16px}.mud-sim-page .mud-data-sim{padding:12px}.mud-sim-page .mud-data-sim-controls label{flex-basis:100%}.mud-sim-page .mud-data-sim-controls select{flex:1;min-width:0}.mud-sim-page .mud-data-sim-controls .mud-btn{flex:1}.mud-sim-page .mud-sim-status{flex-direction:column;gap:3px}}
`;
return view.extend({
    load:function() { return Promise.all([M.callSimGet(),get()]); },
    render:function(data) {
        M.injectCss(); M.localizeMenu();
        var self=this, root=this.root=el('div',null,'mud mud-sim-page');
        root.append(el('style',CSS));
        var panel=el('section',null,'mud-card mud-sim-panel'); root.append(panel);
        panel.append(el('h3',M.translate('SIM 卡管理')));
        panel.append(el('p',M.translate('切换上网卡后，看板、锁定和 AT 的查看卡槽会同步；仍可手动查看另一张卡。'),'mud-note mud-sim-intro'));
        var controls=el('div',null,'mud-data-sim'); panel.append(controls);
        var actual=el('span'), saved=el('span'), connection=el('span'), select=el('select'), button=el('button',M.translate('切换上网卡'),'mud-btn');
        select.id='mud-data-sim-select'; button.type='button';
        [0,1].forEach(function(n) { var o=el('option',card(n)); o.value=n; select.append(o); });
        var row=el('div',null,'mud-data-sim-controls');
        var label=el('label',M.translate('默认上网卡')); label.htmlFor=select.id;
        row.append(label,select,button); controls.append(row);
        var summary=el('div',null,'mud-sim-status'); summary.append(actual,connection,saved); controls.append(summary);
        controls.append(el('p',M.translate('切换会短暂中断蜂窝网络，成功后作为开机默认上网卡；不会切换 USB 或 Wi-Fi。'),'mud-note'));
        controls.append(el('p',M.translate(data[1].native ? 'U30 Air 每次仅启用一张卡的射频。目标卡无数据且原卡有数据时，会恢复原卡；开机默认卡只在连接成功后自动保存。' : '欠费或无信号不影响选卡；数据连接失败不会自动切回。'),'mud-note'));
        var nativeBox=null, nativeHot=null, nativeSave=null, nativeNote=null, last=data[1];
        if(data[1].native) {
            nativeBox=el('div',null,'mud-data-sim'); panel.append(nativeBox);
            nativeBox.append(el('h3',M.translate('U30 Air 原生双卡')));
            var hotLabel=el('label',null,'mud-data-sim-controls'); nativeHot=el('input'); nativeHot.type='checkbox';
            hotLabel.append(nativeHot,el('span',M.translate('启用双卡热切换（首次启用后需重启）'))); nativeBox.append(hotLabel);
            nativeNote=el('p',null,'mud-note'); nativeBox.append(nativeNote);
            nativeSave=el('button',M.translate('仅保存为下次开机默认卡'),'mud-btn'); nativeSave.type='button'; nativeBox.append(nativeSave);
            nativeBox.append(el('p',M.translate('关闭热切换时仍可选择下次开机使用的 SIM。此设置不会立即切卡或重启。'),'mud-note'));
            nativeHot.onchange=function(){configure('u30-hot-'+(nativeHot.checked?'1':'0'),nativeHot);};
            nativeSave.onclick=function(){configure('u30-default-'+select.value,nativeSave);};
        }
        function paint(r,initial) {
            last=r;
            button.disabled=data[0].slots!==2 || !r.ok || r.ready===false || !!self.busy;
            if(nativeHot)nativeHot.checked=r.hot===1;
            if(nativeNote) {
                var ns=r.native_status||{}, note='';
                if(ns.result==='reboot_required'||ns.result==='restarting')note='射频状态需要重启恢复，请保留当前开机默认卡';
                else if(ns.fallback)note='上次双卡启动未完成，已回退 SIM1';
                else if(r.hot===1 && r.ready===false)note='双卡通道尚未就绪；首次启用后请重启';
                nativeNote.textContent=M.translate(note); nativeNote.hidden=!note;
            }
            actual.textContent=M.translate('当前上网卡')+'：'+card(r.actual_sim);
            saved.textContent=M.translate('开机默认')+'：'+card(r.saved_sim);
            connection.textContent=M.translate('数据连接')+'：'+M.translate(r.data_connected?'已连接':'未连接');
            if(initial)select.value=r.saved_sim===1?'1':'0';
        }
        paint(data[1],true);
        button.disabled=data[0].slots!==2 || !data[1].ok || data[1].ready===false;
        select.disabled=data[0].slots!==2 || !data[1].ok;
        if(button.disabled && !data[1].native)panel.append(el('p',message(data[1].ready===false && data[0].slots===2?'dual_boot_required':'dual_sim_unavailable'),'mud-note'));
        function wait(id) {
            return new Promise(function(resolve,reject) {
                self.cancelWait=function(){reject(new Error('页面已关闭'));};
                var deadline=performance.now()+(data[1].native?360000:240000);
                function next() {
                    if(!root.isConnected)return reject(new Error('页面已关闭'));
                    if(performance.now()>deadline)return reject(new Error('应用超时，请刷新确认模组状态'));
                    status(id).then(function(r) {
                        if(r.id!==id || r.state==='error')return reject(new Error(r.error||'网络设置执行失败'));
                        if(r.state==='done' && r.ok)return resolve(r);
                        self.timer=setTimeout(next,1000);
                    }).catch(reject);
                }
                next();
            });
        }
        function configure(target,control) {
            if(self.busy)return;
            self.busy=true; control.disabled=true; button.disabled=true; select.disabled=true;
            if(nativeHot)nativeHot.disabled=true;
            if(nativeSave)nativeSave.disabled=true;
            start(target).then(function(r){if(!r.ok||!r.id)throw new Error(r.error||'网络设置提交失败');return wait(r.id);})
                .then(function(){M.toast('双卡开机设置已保存；需要时请手动重启',{type:'success'});})
                .catch(function(e){if(root.isConnected)M.toast(message(e.message),{type:'error'});})
                .finally(function(){self.busy=false;select.disabled=false;if(nativeHot)nativeHot.disabled=false;if(nativeSave)nativeSave.disabled=false;
                    if(root.isConnected)get().then(function(r){if(root.isConnected)paint(r,true);}).catch(function(){});});
        }
        button.onclick=function() {
            if(self.busy)return;
            var target=select.value; self.busy=true;
            M.confirmBox('切换上网卡？',M.translate('目标卡槽')+'：'+card(Number(target)),{danger:true}).then(function(yes) {
                if(!yes || !root.isConnected)return;
                M.busy(button,true); select.disabled=true; if(nativeHot)nativeHot.disabled=true; if(nativeSave)nativeSave.disabled=true;
                var toast=M.toast('正在切换上网卡…',{type:'busy',timeout:0});
                return start(target).then(function(r) {
                    if(!r.ok || !r.id)throw new Error(r.error||'网络设置提交失败');
                    return wait(r.id);
                }).then(function() { M.selectViewedSlot(target); M.toast('上网卡切换完成',{type:'success'}); })
                  .catch(function(e) { if(root.isConnected)M.toast(message(e.message),{type:'error'}); })
                  .finally(function() { toast.close(); M.busy(button,false); select.disabled=false; if(root.isConnected)return get().then(function(r){if(root.isConnected)paint(r,true);}).catch(function(){}); });
            }).finally(function(){self.busy=false; if(nativeHot)nativeHot.disabled=false; if(nativeSave)nativeSave.disabled=false; button.disabled=last.ready===false;});
        };
        this.refresh=function() {
            if(document.hidden||!root.isConnected||self.busy||self.inflight)return Promise.resolve();
            self.inflight=true;
            return get().then(function(r){if(root.isConnected)paint(r,false);}).catch(function(){}).finally(function(){self.inflight=false;});
        };
        poll.add(this.refresh,2);
        return root;
    },
    unload:function(){poll.remove(this.refresh); clearTimeout(this.timer); if(this.cancelWait)this.cancelWait();},
    handleSaveApply:null,handleSave:null,handleReset:null
});
