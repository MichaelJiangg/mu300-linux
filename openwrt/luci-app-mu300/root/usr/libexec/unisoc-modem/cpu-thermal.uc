// Standard thermal sysfs only. No sensor numbers, PMIC writes or AT dependencies.
import * as fs from 'fs';
const ROOT=getenv('MU300_THERMAL_SYS') || '/sys/class/thermal';
function text(path) { return trim(fs.readfile(path) || ''); }
function num(path) { let v=text(path); return match(v,/^-?[0-9]+$/)?int(v):null; }
export function zones() {
    let out=[];
    for (let id in sort(fs.lsdir(ROOT) || [])) {
        if (!match(id,/^thermal_zone[0-9]+$/)) continue;
        let path=ROOT+'/'+id, cooling=[], trips=[];
        for (let entry in sort(fs.lsdir(path) || [])) {
            if (!match(entry,/^cdev[0-9]+$/)) continue;
            let kind=text(path+'/'+entry+'/type');
            if (!length(kind)) continue;
            push(cooling,{id:entry,type:kind,state:num(path+'/'+entry+'/cur_state'),max_state:num(path+'/'+entry+'/max_state'),trip:num(path+'/'+entry+'_trip_point'),cpu:!!match(kind,/^cpufreq/)});
        }
        for (let entry in fs.lsdir(path) || []) {
            let m=match(entry,/^trip_point_([0-9]+)_temp$/);
            if (!m) continue;
            let index=int(m[1]), kind=text(path+'/trip_point_'+index+'_type'), value=num(path+'/'+entry);
            push(trips,{id:index,type:kind,temp:value,hysteresis:num(path+'/trip_point_'+index+'_hyst'),
                throttles_cpu:!!length(filter(cooling,c=>c.cpu && c.trip==index)),
                writable:kind=='passive' && value!=null && !!length(filter(cooling,c=>c.cpu)) && !!(fs.stat(path+'/'+entry)?.mode & 128) && text(path+'/mode')!='disabled'});
        }
        trips=sort(trips,(a,b)=>a.id-b.id);
        let critical=map(filter(trips,t=>(t.type=='critical'||t.type=='hot') && t.temp!=null),t=>t.temp-10000);
        let maximum=100000; for (let c in critical) if(c<maximum) maximum=c;
        push(out,{id,name:text(path+'/type'),temp:num(path+'/temp'),mode:text(path+'/mode'),policy:text(path+'/policy'),
            minimum:40000,maximum,step:1000,trips,cooling});
    }
    return out;
};
export function settings(current) {
    let out=[];
    for (let z in current) for (let t in z.trips) if(t.writable) push(out,{zone:z.name,trip:t.id,temp:t.temp});
    return out;
};
export function cpu_clamped(id) {
    let kind='cpufreq-cpu'+substr(id,6);
    return !!length(filter(zones(),z=>length(filter(z.cooling,c=>c.type==kind && c.state>0))));
};
export function plan(input,current) {
    if(type(input)!='array' || length(input)>128) die('温控配置无效');
    let seen={}, steps=[];
    for(let item in input) {
        if(type(item)!='object' || length(keys(item))!=3 || type(item.zone)!='string' || type(item.trip)!='int' || type(item.temp)!='int') die('温控配置无效');
        let found=filter(current,z=>z.name==item.zone);
        if(length(found)!=1) die('温区不存在或名称不唯一');
        let z=found[0], t=filter(z.trips,t=>t.id==item.trip)[0], key=z.id+':'+item.trip;
        if(!t?.writable || seen[key]) die('只能调整可写的 CPU 被动温控阈值');
        if(item.temp<z.minimum || item.temp>z.maximum || item.temp%z.step) die('温控阈值超出保护范围');
        seen[key]=true;
        push(steps,{path:ROOT+'/'+z.id+'/trip_point_'+t.id+'_temp',before:t.temp,value:item.temp,zone:z.id,trip:t.id});
    }
    for(let z in current) {
        if(!length(filter(steps,s=>s.zone==z.id))) continue;
        let previous=null;
        for(let t in z.trips) {
            if(t.type!='passive') continue;
            let change=filter(steps,s=>s.zone==z.id && s.trip==t.id)[0], temp=change?change.value:t.temp;
            if(temp==null || (previous!=null && temp-previous<1000)) die('被动温控阈值必须至少相隔 1°C 并递增');
            previous=temp;
        }
    }
    // Lower low trips first; raise high trips first. Intermediate ordering is safe too.
    return sort(steps,(a,b)=>{
        let da=a.value<a.before, db=b.value<b.before;
        if(da!=db) return da?-1:1;
        return da?a.trip-b.trip:b.trip-a.trip;
    });
};
export function write(step,restore) {
    let value=restore?step.before:step.value, str=''+value;
    return fs.writefile(step.path,str+'\n')==length(str)+1 && num(step.path)==value;
};
