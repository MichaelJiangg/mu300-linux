// Isolated integration test, also safe on a router: only a new /tmp directory,
// fake network counters and a unique test ubus object are mutated. Never calls
// the production unisoc.traffic clear method. An optional ledger is READ/copied.
import * as fs from 'fs';
import * as core from 'traffic-core';
const lib = getenv('MU300_TEST_TRAFFIC_LIB') || '/src/openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem';
const rpcfile = getenv('MU300_TEST_RPC') || '/src/openwrt/luci-app-mu300/root/usr/libexec/rpcd/mu300dash';
let checks = 0, pid = null;
function check(ok, label) { if (!ok) die('FAIL: ' + label + '\n'); checks++; }
function quote(s) { return "'" + replace(s, /'/g, "'\\''") + "'"; }
function run(cmd) {
    let p = fs.popen(cmd, 'r'), out = p.read('all'), code = p.close();
    return { out: out, code: code };
}
const root = trim(run('mktemp -d /tmp/mu300-traffic-test.XXXXXX').out);
check(match(root, /^\/tmp\/mu300-traffic-test\.[a-zA-Z0-9]+$/), 'private test directory');
const base = root + '/disk', ram = root + '/ram', net = root + '/net';
const bus = 'unisoc.traffic.test.' + substr(root, length('/tmp/mu300-traffic-test.'));
// Run the unchanged RPC shell script, redirecting ONLY its private traffic
// calls to our fixture object. All other stub ubus calls fail closed.
const real_ubus = trim(run('command -v ubus').out);
check(substr(real_ubus,0,1)=='/' && fs.stat(rpcfile), 'RPC fixture prerequisites');
fs.mkdir(root+'/bin',448);
fs.writefile(root+'/bin/ubus', '#!/bin/sh\n[ "$1" = -t ] && [ "$3" = call ] && [ "$4" = unisoc.traffic ] || exit 99\nshift 4\nexec '+quote(real_ubus)+' -t 5 call '+quote(bus)+' "$@"\n');
fs.chmod(root+'/bin/ubus',448);
for (let dir in [base,ram,net,net+'/fake0',net+'/fake0/statistics',net+'/fake1',net+'/fake1/statistics']) fs.mkdir(dir,448);
function counter(dev, rx, tx, idx) {
    fs.writefile(net+'/'+dev+'/statistics/rx_bytes', ''+rx);
    fs.writefile(net+'/'+dev+'/statistics/tx_bytes', ''+tx);
    fs.writefile(net+'/'+dev+'/ifindex', ''+idx);
}
counter('fake0',1000000,2000000,31); counter('fake1',3000000,4000000,32);
let seedpath = getenv('MU300_TEST_LEDGER');
let db = seedpath ? json(fs.readfile(seedpath)) : core.fresh(time());
db.config = core.config(db.config); db.config.device = 'fake0';
db.last = null;
db.days[core.day_key(time())] = {rx:123456,tx:654321};
db.months[substr(core.day_key(time()),0,7)] = {rx:9876543,tx:7654321};
db.adjustment = {start:core.cycle(time(),db.config.reset_day).start,
    reset_day:db.config.reset_day,mode:db.config.count_mode,bytes:777};
fs.writefile(base+'/state.json',sprintf('%J',db));
function call(method, input) {
    let r = run('ubus -t 3 call '+quote(bus)+' '+quote(method)+' '+quote(sprintf('%J',input || {})));
    check(r.code==0, 'RPC '+method);
    return json(r.out);
}
function rpc(method, input) {
    let r=run('printf %s '+quote(sprintf('%J',input))+' | PATH='+quote(root+'/bin')+':"$PATH" sh '+quote(rpcfile)+' call '+quote(method));
    check(r.code==0,'frontend RPC '+method);
    return json(r.out);
}
function start() {
    let r = run('MU300_TRAFFIC_DIR='+quote(base)+' MU300_TRAFFIC_RUN='+quote(ram)+
        ' MU300_TRAFFIC_SIM_SLOTS=1 MU300_TRAFFIC_SYS='+quote(net)+' MU300_TRAFFIC_BUS='+quote(bus)+
        ' ucode '+quote(lib+'/traffic')+' >'+quote(root+'/daemon.log')+' 2>&1 & echo $!');
    pid=int(trim(r.out)); check(pid>1,'test worker PID');
    for(let i=0;i<10;i++) {
        if(trim(run('ubus -S list '+quote(bus)).out)==bus) return;
        run('sleep 1');
    }
    die('Test service failed to start: '+fs.readfile(root+'/daemon.log')+'\n');
}
function stop() {
    if(!pid) return;
    run('kill -TERM '+pid);
    for(let i=0;i<10;i++) {
        if(trim(run('ubus -S list '+quote(bus)).out)=='') {pid=null;return;}
        run('sleep 1');
    }
    die('Test service did not stop\n');
}
try {
    start();
    let before=call('get'), disk=fs.readfile(base+'/state.json');
    check(before.status.today.rx==123456,'seed copied history');
    check(call('clear').error=='confirmation_required','missing confirmation rejected');
    check(call('clear',{confirm:false}).error=='confirmation_required','cancel rejected');
    check(fs.readfile(base+'/state.json')==disk,'cancel leaves saved ledger unchanged');
    fs.mkdir(base+'/state.json.new',448);
    check(call('clear',{confirm:true}).error=='storage_failed','disk failure reported');
    check(call('get').status.today.rx==123456,'failed clear preserves memory');
    check(fs.readfile(base+'/state.json')==disk,'failed clear preserves disk');
    fs.rmdir(base+'/state.json.new');
    // Force RAM checkpoint failure AFTER a durable commit. Restart must choose
    // the newer disk revision, not resurrect the old RAM history.
    fs.mkdir(ram+'/state.json.new',448);
    let cleared=call('clear',{confirm:true});
    check(cleared.ok && cleared.data.status.today_used==0 && cleared.data.status.cycle_used==0,'durable clear');
    check(sprintf('%J',cleared.data.config)==sprintf('%J',before.config),'saved plan retained');
    check(cleared.data.status.storage_error,'RAM checkpoint error visible');
    counter('fake0',1000100,2000020,31);
    call('flush');
    let after=call('get');
    check(after.status.today.rx==100 && after.status.today.tx==20,'post-clear traffic only');
    stop(); fs.rmdir(ram+'/state.json.new'); start();
    after=call('get');
    check(after.status.today.rx==100 && after.status.today.tx==20,'stale RAM cannot undo committed clear');
    check(!after.status.storage_error,'storage recovers');
    check(call('clear',{confirm:true}).ok,'second clear succeeds');
    check(call('get').status.month_used==0,'month cleared');
    let cfg=before.config; cfg.device='fake1';
    check(call('set',{payload:sprintf('%J',cfg)}).ok,'configurable interface preserved');
    check(call('get').status.today_used==0,'interface change establishes baseline');
    counter('fake1',3000030,4000010,32); call('flush');
    after=call('get');
    check(after.status.today.rx==30 && after.status.today.tx==10,'new interface delta');
    // Browser calls carry a session. It belongs to mu300dash ACL checking,
    // not to the internal service, where forwarding it would deny the call.
    const session='00000000000000000000000000000000';
    check(rpc('traffic_clear',{confirm:false,ubus_rpc_session:session}).error=='confirmation_required','browser cancel guarded');
    check(rpc('traffic_set',{payload:'invalid-json',ubus_rpc_session:session}).error=='invalid_config','browser invalid config reaches validator');
    check(rpc('traffic_set',{payload:sprintf('%J',cfg),ubus_rpc_session:session}).ok,'browser settings save');
    check(rpc('traffic_clear',{confirm:true,ubus_rpc_session:session}).ok,'browser clear transaction');
    check(call('get').status.today_used==0,'browser transaction actually cleared fixture');
    stop();
} catch(e) {
    stop(); die('Traffic integration: '+e+'; fixtures '+root+'\n');
}
printf('traffic service: %d checks passed; isolated fixtures %s\n',checks,root);
