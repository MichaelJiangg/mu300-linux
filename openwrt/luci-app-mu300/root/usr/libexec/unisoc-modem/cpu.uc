// Standard cpufreq and passive thermal trips; voltage is a separate backend.
import * as fs from 'fs';
import * as thermal from './cpu-thermal.uc';
const ROOT=getenv('MU300_CPU_SYS') || '/sys/devices/system/cpu/cpufreq';
const CONFIG=getenv('MU300_CPU_CONFIG') || '/etc/unisoc-modem/cpu.json';
const DEFAULTS=getenv('MU300_CPU_DEFAULTS') || '/run/unisoc-cpu-defaults.json';
const BOOT=getenv('MU300_CPU_BOOT_ID') || '/proc/sys/kernel/random/boot_id';
let failed_write=null;
function read(id,key) { return trim(fs.readfile(ROOT+'/'+id+'/'+key) || ''); }
function words(s) { return length(trim(s)) ? split(trim(s), /\s+/) : []; }
function number(id,key) { let v=read(id,key); return match(v,/^[0-9]+$/)?int(v):null; }
function policies() {
    let out=[];
    for(let id in sort(fs.lsdir(ROOT) || [])) {
        if(!match(id,/^policy[0-9]+$/)) continue;
        let p={id,cpus:read(id,'affected_cpus'),driver:read(id,'scaling_driver'),
            governors:words(read(id,'scaling_available_governors')),governor:read(id,'scaling_governor'),
            min:number(id,'scaling_min_freq'),max:number(id,'scaling_max_freq'),
            hardware_min:number(id,'cpuinfo_min_freq'),hardware_max:number(id,'cpuinfo_max_freq'),
            current:number(id,'scaling_cur_freq'),frequencies:map(words(read(id,'scaling_available_frequencies')),v=>int(v))};
        p.writable=!!length(p.governors) && p.min!=null && p.max!=null && p.hardware_min!=null && p.hardware_max!=null;
        push(out,p);
    }
    return out;
}
function saved() {
    let raw=fs.readfile(CONFIG);
    if(raw==null && !fs.stat(CONFIG)) return {version:2};
    let config=json(raw);
    if(config?.version==2) return config;
    if(config?.version!=1) die('CPU 配置无效');
    // Read-only compatibility: migrate a combined profile on the next save.
    let converted={version:2};
    if(config.persist===true) {
        if(length(config.changes || [])) converted.frequency={changes:config.changes};
        if(length(config.thermal || [])) converted.thermal={thermal:config.thermal};
    }
    return converted;
}
function persist_flags(config) { return {persist:config.frequency!=null,thermal_persist:config.thermal!=null}; }
function save_scope(config,scope,profile) {
    if(profile==null) delete config[scope]; else config[scope]=profile;
    if(config.frequency==null && config.thermal==null) return !fs.stat(CONFIG) || fs.unlink(CONFIG);
    let text=sprintf('%J\n',config), tmp=CONFIG+'.new';
    if(fs.writefile(tmp,text)==length(text) && fs.chmod(tmp,384) && fs.rename(tmp,CONFIG)) return true;
    fs.unlink(tmp); return false;
}
function baseline(current,zones) {
    let id=trim(fs.readfile(BOOT) || ''), stored=null;
    if(!length(id)) die('无法读取 CPU 启动基线');
    try { stored=json(fs.readfile(DEFAULTS) || 'null'); } catch(e) {}
    if(stored?.boot==id) {
        // A deferred sensor may appear after S99. Capture newly available trips
        // before their first edit, never replace this boot's existing baseline.
        let added=false;
        for(let t in thermal.settings(zones)) if(!length(filter(stored.thermal,x=>x.zone==t.zone && x.trip==t.trip))) {
            push(stored.thermal,t); added=true;
        }
        if(!added) return stored;
    } else stored={boot:id,changes:map(filter(current,p=>p.writable),p=>({id:p.id,cpus:p.cpus,governor:p.governor,min:p.min,max:p.max})),thermal:thermal.settings(zones)};
    let text=sprintf('%J\n',stored), tmp=DEFAULTS+'.new';
    if(fs.writefile(tmp,text)!=length(text) || !fs.chmod(tmp,384) || !fs.rename(tmp,DEFAULTS)) {
        fs.unlink(tmp); die('无法保存 CPU 启动基线');
    }
    return stored;
}
function write(id,key,value) {
    let s=''+value;
    if(read(id,key)==s) return true;
    let written=fs.writefile(ROOT+'/'+id+'/'+key,s+'\n'), actual=read(id,key);
    // cpufreq QoS queues policy work; successful sysfs write is acceptance,
    // not completion. Confirm the queued update without reissuing the write.
    // Only explicit setting changes use this bounded, sleeping confirmation.
    for(let n=0; written==length(s)+1 && actual!=s && n<10; n++) {
        sleep(10); actual=read(id,key);
    }
    let ok=written==length(s)+1 && actual==s;
    // scaling_max_freq reports the effective policy cap, not the caller's QoS
    // request. A successfully accepted max request may remain thermally capped.
    if(!ok && key=='scaling_max_freq' && written==length(s)+1 &&
       match(actual,/^[0-9]+$/) && int(actual)<int(s) && thermal.cpu_clamped(id)) ok=true;
    if(!ok && !failed_write) failed_write={policy:id,field:key,requested:s,actual,written};
    return ok;
}
function set(p,c) {
    // Raise max before min, or lower min before max, to avoid transient EINVAL.
    if(c.min>number(p.id,'scaling_max_freq')) {
        if(!write(p.id,'scaling_max_freq',c.max) || !write(p.id,'scaling_min_freq',c.min)) return false;
    } else {
        if(!write(p.id,'scaling_min_freq',c.min) || !write(p.id,'scaling_max_freq',c.max)) return false;
    }
    return write(p.id,'scaling_governor',c.governor);
}
function apply(input,replay) {
    let current=policies(), zones=thermal.zones(), byid={}, seen={}, steps;
    for(let p in current) byid[p.id]=p;
    if(type(input)!='object') return {ok:0,error:'CPU 配置无效'};
    let scope=input.scope || 'frequency', config=saved();
    if(scope!='frequency' && scope!='thermal') return {ok:0,error:'CPU 配置无效'};
    // A stale combined UI must never apply or erase the other section.
    if((scope=='frequency' && input.thermal!=null) || (scope=='thermal' && input.changes!=null))
        return {ok:0,error:'请刷新页面后分别应用频率或温控设置'};
    if(input.reset===true) {
        let base=baseline(current,zones);
        input=scope=='frequency'?{changes:base.changes,persist:false}:{thermal:base.thermal,persist:false};
    }
    let changes=scope=='frequency'?input.changes:[], trips=scope=='thermal'?input.thermal:[];
    if(type(input.persist)!='bool' || type(changes)!='array' || length(changes)>32 ||
       (scope=='frequency' && !length(changes)) || (scope=='thermal' && !length(trips || [])))
        return {ok:0,error:'CPU 配置无效'};
    try { steps=thermal.plan(trips,zones); } catch(e) { return {ok:0,error:e.message || ''+e}; }
    for(let c in changes) {
        let p=byid[c?.id];
        if(!p?.writable || seen[c.id] || c.cpus!=p.cpus || type(c.min)!='int' || type(c.max)!='int' ||
           c.min>c.max || c.min<p.hardware_min || c.max>p.hardware_max || index(p.governors,c.governor)<0 ||
           (length(p.frequencies) && (index(p.frequencies,c.min)<0 || index(p.frequencies,c.max)<0)))
            return {ok:0,error:'CPU 配置无效'};
        seen[c.id]=true;
    }
    baseline(current,zones);
    let desired=map(filter(current,p=>p.writable),p=>({id:p.id,cpus:p.cpus,governor:p.governor,min:p.min,max:p.max}));
    // Retain saved QoS requests when only thermal settings are edited; never
    // replace them with the temporary caps produced by the thermal governor.
    for(let c in (config.frequency?.changes || [])) for(let p in desired) if(p.id==c.id && p.cpus==c.cpus) {
        p.governor=c.governor; p.min=c.min; p.max=c.max;
    }
    for(let c in changes) for(let p in desired) if(p.id==c.id) {
        p.governor=c.governor; p.min=c.min; p.max=c.max;
    }
    let changed=[], thermal_changed=[], error=null, rollback=true;
    for(let c in changes) {
        let p=byid[c.id]; push(changed,p);
        if(!set(p,c)) { error='CPU 配置回读不一致'; break; }
    }
    if(!error) for(let step in steps) {
        push(thermal_changed,step);
        if(!thermal.write(step,false)) { error='温控配置回读不一致'; break; }
    }
    if(!error && !replay) {
        let profile=scope=='frequency'?{changes:desired}:{thermal:thermal.settings(thermal.zones())};
        if(!save_scope(config,scope,input.persist?profile:null)) error='无法保存 CPU 设置';
    }
    if(error) {
        for(let step in reverse(thermal_changed)) if(!thermal.write(step,true)) rollback=false;
        for(let p in reverse(changed)) if(!set(p,p)) rollback=false;
        return {ok:0,error,rollback,failed_write};
    }
    let flags=persist_flags(saved());
    return {ok:1,scope,policies:policies(),zones:thermal.zones(),persist:flags.persist,thermal_persist:flags.thermal_persist};
}
let action=ARGV[0] || 'get', result;
try {
    if(action=='get') {
        let flags=persist_flags(saved());
        result={ok:1,policies:policies(),zones:thermal.zones(),persist:flags.persist,thermal_persist:flags.thermal_persist};
    }
    else if(action=='forget') result=save_scope(saved(),'frequency',null) ? {ok:1,persist:false} : {ok:0,error:'无法保存 CPU 设置'};
    else if(action=='boot') {
        baseline(policies(),thermal.zones());
        let config=saved();
        let frequency={ok:1,skipped:true}, therm={ok:1,skipped:true};
        // Each domain replays independently; missing thermal support must not
        // prevent restoring frequency settings (or vice versa).
        if(config.frequency!=null) try { frequency=apply({scope:'frequency',changes:config.frequency.changes,persist:true},true); }
            catch(e) { frequency={ok:0,error:'CPU 配置无效'}; }
        if(config.thermal!=null) try { therm=apply({scope:'thermal',thermal:config.thermal.thermal,persist:true},true); }
            catch(e) { therm={ok:0,error:'温控配置无效'}; }
        result={ok:frequency.ok && therm.ok?1:0,frequency,thermal:therm};
    } else if(action=='apply') {
        let text=fs.stdin.read(16385);
        result=length(text)>16384?{ok:0,error:'CPU 配置无效'}:apply(json(text));
    } else result={ok:0,error:'CPU 配置无效'};
} catch(e) { result={ok:0,error:'CPU 配置无效'}; }
print(sprintf('%J\n',result));
exit(result.ok?0:1);
