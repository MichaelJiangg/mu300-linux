// Real ucode/ubus integration against private files and fake counters only.
import * as fs from 'fs';
import * as core from 'traffic-core';
const lib=getenv('MU300_TEST_TRAFFIC_LIB') || '/src/openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem';
let checks=0,pid=null;
function check(ok,label){if(!ok)die('FAIL '+label+'\n'); checks++;}
function q(s){return "'"+replace(s,/'/g,"'\\''")+"'";}
function run(s){let p=fs.popen(s,'r'),out=p.read('all'),code=p.close();return {out:out,code:code};}
const root=trim(run('mktemp -d /tmp/mu300-traffic-dual.XXXXXX').out);
check(match(root,/^\/tmp\/mu300-traffic-dual\.[a-zA-Z0-9]+$/),'test root');
const base=root+'/disk',ram=root+'/ram',net=root+'/net',bus='unisoc.traffic.dual.'+substr(root,-6);
for(let d in [base,ram,net,net+'/fake0',net+'/fake1',net+'/fake0/statistics',net+'/fake1/statistics'])fs.mkdir(d,448);
function counter(dev,rx,tx){fs.writefile(net+'/'+dev+'/ifindex',dev=='fake0'?'31':'32');fs.writefile(net+'/'+dev+'/statistics/rx_bytes',''+rx);fs.writefile(net+'/'+dev+'/statistics/tx_bytes',''+tx);}
counter('fake0',1000000,2000000);counter('fake1',3000000,4000000);
let seed=core.fresh(time());seed.days[core.day_key(time())]={rx:1234,tx:4321};
fs.writefile(base+'/state.json',sprintf('%J',seed));
function call(method,args){let r=run('ubus -t 3 call '+q(bus)+' '+q(method)+' '+q(sprintf('%J',args||{})));check(r.code==0,'call '+method);return json(r.out);}
function start(){
    let r=run('MU300_TRAFFIC_DIR='+q(base)+' MU300_TRAFFIC_RUN='+q(ram)+' MU300_TRAFFIC_SYS='+q(net)+' MU300_TRAFFIC_BUS='+q(bus)+' MU300_TRAFFIC_SIM_SLOTS=2 MU300_TRAFFIC_DEVICES='+q('["fake0","fake1"]')+' ucode '+q(lib+'/traffic')+' >'+q(root+'/log')+' 2>&1 & echo $!');
    pid=int(trim(r.out));check(pid>1,'child');
    for(let i=0;i<10;i++){if(trim(run('ubus -S list '+q(bus)).out)==bus)return; sleep(100);}
    die(fs.readfile(root+'/log'));
}
function stop(){if(pid){run('kill -TERM '+pid);for(let i=0;i<20;i++){if(trim(run('ubus -S list '+q(bus)).out)==''){pid=null;return;}sleep(100);}die('stop failed\n');}}
try{
    start();
    check(call('get',{slot:0}).status.today.rx==1234,'legacy ledger retained');
    check(call('get',{slot:1}).status.today_used==0,'no duplicated old usage');
    counter('fake0',1000100,2000020);counter('fake1',3000500,4000030);call('flush');
    check(call('get',{slot:0}).status.today.rx==1334,'SIM 1 delta');
    check(call('get',{slot:1}).status.today.rx==500,'SIM 2 delta');
    let cfg=call('get',{slot:1}).config;cfg.monthly_gb=77;
    check(call('set',{slot:1,payload:sprintf('%J',cfg)}).ok,'SIM 2 plan');
    check(call('clear',{slot:1,confirm:true}).ok,'SIM 2 clear');
    check(call('get',{slot:0}).status.today.rx==1334,'other ledger untouched');
    check(call('get',{slot:1}).status.today_used==0,'SIM 2 clear baseline');
    counter('fake1',3000600,4000050);call('flush');stop();start();
    check(call('get',{slot:1}).status.today.rx==100,'restart preserves post-clear delta');
    check(call('get',{slot:0}).status.today.rx==1334,'restart keeps old card ledger');
    cfg=call('get',{slot:1}).config;cfg.device='fake0';
    check(call('set',{slot:1,payload:sprintf('%J',cfg)}).ok,'duplicate mapping accepted but paused');
    check(call('get',{slot:1}).status.mapping_error,'duplicate mapping visible');
    counter('fake0',1001100,2000020);call('flush');
    check(call('get',{slot:1}).status.today.rx==100,'duplicate mapping not double counted');
    check(call('get',{slot:2}).error=='invalid_sim','invalid card rejected');
    stop();
}catch(e){stop();die('Dual traffic: '+e+' '+root+'\n');}
printf('PASS %d dual traffic checks: %s\n',checks,root);
