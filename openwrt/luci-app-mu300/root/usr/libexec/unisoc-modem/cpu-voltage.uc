// Boot-only voltage profiles. No arbitrary shell arguments, live voltage
// writes, AT access, polling worker, or firmware/boot partition modifications.
import * as fs from 'fs';
const DIR=getenv('MU300_CPU_VOLTAGE_DIR') || '/etc/unisoc-modem';
const RUN=getenv('MU300_CPU_VOLTAGE_RUN') || '/run';
const ROOT=getenv('MU300_CPU_SYS') || '/sys/devices/system/cpu/cpufreq';
const CONFIG=DIR+'/cpu-voltage.json', ARMED=DIR+'/cpu-voltage-armed.json';
const BOOT=trim(fs.readfile(getenv('MU300_CPU_BOOT_ID') || '/proc/sys/kernel/random/boot_id') || '');
const PLATFORM=getenv('MU300_CPU_PLATFORM') || '/opt/mu300/bin/cpu-voltage-platform';
function readjson(path) { try { return json(fs.readfile(path) || 'null'); } catch(e) { return null; } }
function valid(v) {
    if(type(v)!='array' || length(v)!=3) return false;
    for(let n in v) if(type(n)!='int' || n < -50000 || n > 25000 || n%3125) return false;
    return true;
}
function store(path,value) {
    let s=sprintf('%J\n',value), tmp=path+'.new';
    fs.mkdir(DIR,448);
    if(fs.writefile(tmp,s)!=length(s) || !fs.chmod(tmp,384) || !fs.rename(tmp,path)) {
        fs.unlink(tmp); return false;
    }
    return true;
}
function supported(force) {
    let cache=RUN+'/unisoc-cpu-firmware.json', c=readjson(cache);
    if(!force && BOOT && c?.boot==BOOT) return c.supported===true;
    // Only the installed platform adapter knows its verified SML hashes.
    // Environment overrides are test-only, never RPC/user configuration.
    if(!fs.access(PLATFORM,'x') || !match(PLATFORM,/^[\/a-zA-Z0-9_.-]+$/)) return false;
    let p=fs.popen(PLATFORM+' check >/dev/null 2>&1','r');
    let ok=p && p.close()==0;
    // Do not pin a transient early-boot discovery failure for the whole boot.
    if(BOOT && ok) store(cache,{boot:BOOT,supported:true});
    return !!ok;
}
function current() {
    let domains=[], seen={};
    for(let id in sort(fs.lsdir(ROOT)||[])) {
        if(!match(id,/^policy[0-9]+$/)) continue;
        let path=ROOT+'/'+id+'/', d=trim(fs.readfile(path+'scaling_voltage_domain')||''),
            offset=trim(fs.readfile(path+'scaling_voltage_offset')||'');
        if(!match(d,/^[012]$/) || !match(offset,/^-?[0-9]+$/) || seen[d]) continue;
        seen[d]=true;
        let table=[];
        for(let line in split(trim(fs.readfile(path+'scaling_voltage_table')||''),'\n')) {
            let pair=match(line,/^([0-9]+) ([0-9]+)$/);
            if(pair) push(table,{khz:int(pair[1]),uv:int(pair[2])});
        }
        push(domains,{id:int(d),policy:id,cpus:trim(fs.readfile(path+'affected_cpus')||''),offset:int(offset),table});
    }
    return domains;
}
function status() {
    let domains=current(), config=readjson(CONFIG), firmware=supported(false);
    let next=config?.version==1 && valid(config.offsets)?config.offsets:[0,0,0];
    return {ok:1,supported:firmware && length(domains)==3,firmware,domains,
        offsets:next,min:-50000,max:25000,step:3125,
        pending:length(filter(domains,d=>d.offset!=next[d.id]))>0,
        recovery:readjson(RUN+'/unisoc-cpu-voltage-recovery.json')?.reason || null};
}
function save(input) {
    if(!valid(input?.offsets)) return {ok:0,error:'CPU 电压配置无效'};
    let nonzero=length(filter(input.offsets,n=>n!=0))>0;
    if(nonzero && (!supported(true) || length(current())!=3)) return {ok:0,error:'当前内核或固件不支持电压调整'};
    if(!store(CONFIG,{version:1,offsets:input.offsets})) return {ok:0,error:'无法保存 CPU 设置'};
    // Do not clear ARMED while running at nonzero voltage, even on reset.
    return status();
}
function bootargs() {
    let config=readjson(CONFIG), armed=readjson(ARMED), reason=null;
    if(fs.stat(ARMED)) {
        if(BOOT && armed?.boot==BOOT) return '0,0,0'; // never apply twice
        reason='unclean_shutdown';
        if(fs.stat(CONFIG) && !fs.rename(CONFIG,CONFIG+'.rejected')) return '0,0,0';
        fs.unlink(ARMED); config=null;
    }
    if(reason) store(RUN+'/unisoc-cpu-voltage-recovery.json',{reason});
    if(config?.version!=1 || !valid(config.offsets) || !length(filter(config.offsets,n=>n!=0))) return '0,0,0';
    if(!BOOT || !supported(true)) return '0,0,0';
    if(!store(ARMED,{boot:BOOT,offsets:config.offsets})) return '0,0,0';
    return join(',',config.offsets);
}
let action=ARGV[0]||'get', result;
try {
    if(action=='boot-args') { print(bootargs()+'\n'); exit(0); }
    if(action=='get') result=status();
    else if(action=='save') {
        let text=fs.stdin.read(4097);
        result=length(text)>4096?{ok:0,error:'CPU 电压配置无效'}:save(json(text));
    } else if(action=='shutdown') {
        let armed=readjson(ARMED);
        result={ok:!fs.stat(ARMED) || (BOOT && armed?.boot==BOOT && fs.unlink(ARMED))?1:0};
    } else result={ok:0,error:'CPU 电压配置无效'};
} catch(e) {
    if(action=='boot-args') { print('0,0,0\n'); exit(0); }
    result={ok:0,error:'CPU 电压配置无效'};
}
print(sprintf('%J\n',result));
exit(result.ok?0:1);
