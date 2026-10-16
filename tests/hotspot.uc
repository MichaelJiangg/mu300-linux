import * as h from 'hotspot';
import * as fs from 'fs';
import { cursor } from 'uci';
let n=0;
function check(ok,label) { if(!ok)die('FAIL '+label+'\n');n++; }
function fixture() {
    let data={radio0:{'.type':'wifi-device',disabled:'0',channel:'1'},
        radio1:{'.type':'wifi-device',disabled:'0',channel:'36'},
        station:{'.name':'station','.type':'wifi-iface',mode:'sta',device:'radio0',ifname:'wlan-sta'},
        guest:{'.name':'guest','.type':'wifi-iface',mode:'ap',device:'radio0',ifname:'guest0',ssid:'Guest'},
        ap:{'.name':'ap','.type':'wifi-iface',mode:'ap',device:'radio1',ifname:'wlan0',ssid:'F50',disabled:'0'}};
    let before=json(sprintf('%J',data));
    let flags={writes:0,commits:0,reverts:0,reloads:0,fail:false,writefail:false,pending:false};
    let c={
        foreach:(cfg,type,fn)=>{for(let k,v in data) if(v['.type']==type)fn(v);},
        get:(cfg,s,k)=>k?data[s]?.[k]:data[s]?.['.type'],
        changes:()=>flags.pending?{wireless:['pending']}:null,
        set:(cfg,s,k,v)=>{flags.writes++;if(flags.writefail)return false;data[s][k]=v;return true;},
        commit:()=>{flags.commits++;return !flags.fail;},
        revert:()=>{flags.reverts++;data=json(sprintf('%J',before));return true;}
    };
    let runtime={radio0:{up:true,interfaces:[{section:'guest',ifname:'guest0'}]},
        radio1:{up:true,interfaces:[{section:'ap',ifname:'wlan0'}]}};
    return {c,data,runtime,flags,reload:()=>{flags.reloads++;return true;}};
}
let f=fixture(), s=h.status(f.c,f.runtime,null,'wlan0');
check(s.section=='ap' && s.radio=='radio1' && s.channel=='36','actual AP/radio not first');
check(s.up && s.enabled,'active status');
check(!h.status(f.c,f.runtime,null,'missing').available,'ambiguous rejected');
check(h.status(f.c,f.runtime,'guest','wlan0').section=='guest','explicit section wins');
check(!h.status(f.c,f.runtime,'station','wlan0').available,'STA selector rejected');
check(!h.status(f.c,f.runtime,'deleted','wlan0').available,'stale selector rejected');
f.data.ap.disabled='1';s=h.status(f.c,f.runtime,null,'wlan0');
check(!s.up && !s.enabled,'AP disabled even with radio enabled');
let r=h.set(f.c,true,f.runtime,null,'wlan0',f.reload);
check(r.ok && r.pending && f.data.ap.disabled=='0','recover disabled AP');
check(f.data.radio0.disabled=='0' && f.data.guest.disabled==null,'other radio and AP unchanged');
check(f.flags.reloads==1,'reload once');
f=fixture();r=h.set(f.c,false,f.runtime,null,'wlan0',f.reload);
check(r.ok && f.data.ap.disabled=='1' && f.data.radio1.disabled=='0','off disables only target AP');
f=fixture();r=h.set(f.c,true,f.runtime,null,'wlan0',f.reload);
check(r.ok && r.unchanged && !f.flags.writes && !f.flags.reloads,'already on is no-op');
f=fixture();f.data.radio1.disabled='1';
r=h.set(f.c,true,f.runtime,null,'wlan0',f.reload);
check(r.ok && f.data.radio1.disabled=='0','enable sole disabled radio');
f=fixture();f.data.radio1.disabled='1';f.data.guest.device='radio1';
r=h.set(f.c,true,f.runtime,'ap','wlan0',f.reload);
check(!r.ok && !f.flags.writes,'shared disabled radio protects other AP');
f=fixture();f.flags.pending=true;
r=h.set(f.c,false,f.runtime,null,'wlan0',f.reload);
check(!r.ok && !f.flags.writes && !f.flags.reverts,'pending user edits preserved');
f=fixture();f.flags.fail=true;
r=h.set(f.c,false,f.runtime,null,'wlan0',f.reload);
check(!r.ok && f.flags.reverts==1 && !f.flags.reloads,'commit failure never reloads');
check(h.status(f.c,f.runtime,null,'wlan0').enabled,'commit failure restores pending config');
f=fixture();r=h.set(f.c,false,f.runtime,null,'wlan0',()=>false);
check(!r.ok && r.saved && f.data.ap.disabled=='1','reload failure honestly reports saved state');
f=fixture();f.runtime.radio1.pending=true;
r=h.set(f.c,false,f.runtime,null,'wlan0',f.reload);
check(!r.ok && !f.flags.writes,'netifd pending rejected');
f=fixture();f.flags.writefail=true;
r=h.set(f.c,false,f.runtime,null,'wlan0',f.reload);
check(!r.ok && !f.flags.commits,'write failure not committed');
f=fixture();f.data.ap.ifname=null;
check(h.status(f.c,f.runtime,null,'wlan0').section=='ap','runtime ifname mapping');
delete f.data.guest;
check(h.status(f.c,{},null,'missing').section=='ap','sole AP works while down');
f.data.ap.device='missing';
check(!h.status(f.c,{},null,'wlan0').available,'missing radio rejected');
delete f.data.ap;
check(!h.status(f.c,{},null,'wlan0').available,'no AP rejected');
check(!h.set(f.c,'on',{},null,'wlan0',f.reload).ok,'invalid parameter rejected');
// Exercise real libuci commit/revert semantics in an isolated configuration.
let pipe=fs.popen('mktemp -d /tmp/mu300-hotspot-test.XXXXXX','r');
let dir=trim(pipe.read('all'));pipe.close();
check(match(dir,/^\/tmp\/mu300-hotspot-test\.[a-zA-Z0-9]+$/),'private UCI fixture');
fs.mkdir(dir+'/delta',448);
fs.writefile(dir+'/wireless', "config wifi-device 'r1'\n option disabled '0'\nconfig wifi-iface 'ap1'\n option device 'r1'\n option mode 'ap'\n option ifname 'wlan0'\n option disabled '1'\n option ssid 'Test only'\n option key 'fixture-secret'\nconfig wifi-iface 'ap2'\n option device 'r1'\n option mode 'ap'\n option disabled '1'\n");
let c=cursor(dir,dir+'/delta'), calls=0;
r=h.set(c,true,{},'ap1','wlan0',()=>{calls++;return true;});
check(r.ok && calls==1,'real UCI commit');
c=cursor(dir,dir+'/delta');
check(c.get('wireless','ap1','disabled')=='0' && c.get('wireless','ap2','disabled')=='1','only selected AP saved');
check(c.get('wireless','ap1','key')=='fixture-secret','password untouched');
c.set('wireless','ap2','ssid','User edit'); check(c.save('wireless'),'save pending fixture');
c=cursor(dir,dir+'/delta');
r=h.set(c,false,{},'ap1','wlan0',()=>{calls++;return true;});
check(!r.ok && calls==1 && c.get('wireless','ap2','ssid')=='User edit','real pending edits protected');
printf('hotspot: %d checks passed\n',n);
