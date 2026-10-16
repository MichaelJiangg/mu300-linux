// ONLY in a throwaway OpenWrt container; never execute on a real router.
// docker run --rm -e MU300_TEST_CONTAINER=1 -v REPO:/src:ro --entrypoint ucode
//   mu300-openwrt-base:25.12.5 /src/tests/dashboard_backport.uc
import { popen, writefile, mkdir, readfile } from 'fs';
if (getenv('MU300_TEST_CONTAINER') != '1') die('Disposable container required\n');
const lib = '/src/openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/';
let checks = 0;
function check(ok, label) { if (!ok) die('FAIL: ' + label + '\n'); checks++; }
function quote(s) { return "'" + replace(s, /'/g, "'\\''") + "'"; }
function run(cmd) {
	const p = popen(cmd, 'r');
	const out = p.read('all');
	check(p.close() == 0, 'command: ' + cmd);
	return out;
}
function operator(reply) { return json(run('ucode ' + lib + 'operator.uc ' + quote(reply))); }
const cases = [
	['+CSCS: "UCS2"\n+COPS: 0,0,"4E2D56FD8054901A",7', '中国联通', null],
	['+CSCS: "UCS2"\n+COPS: 0,1,"00410042",7', 'AB', null],
	['+CSCS: "UCS2"\n+COPS: 0,2,"46001",7', null, '46001'],
	['+CSCS: "IRA"\n+COPS: 0,0,"FACE",7', 'FACE', null],
	['+COPS: 0,0,"00410042",7', '00410042', null],
	['+CSCS: "UCS2"\n+COPS: 0,0,"123",7', '123', null],
	['+CSCS: "UCS2"\n+COPS: 0,0,"D8000041",7', 'D8000041', null],
	['+CSCS: "UCS2"\n+COPS: 0,0,"000A",7', '000A', null],
	['+CSCS: "IRA"\n+COPS: 0,0,"Turkcell",7', 'Turkcell', null]
];
for (let row in cases) {
	const op = operator(row[0]);
	check(op.name == row[1] && op.plmn == row[2] && op.act == 7, 'COPS decoding: ' + row[0]);
}
check(operator('ERROR') == null, 'missing operator');

mkdir('/etc/config');
function config(value, device) {
	writefile('/etc/config/unisoc_modem', "config core 'main'\n option home_refresh_interval '" + value +
		"'\n option data_device '" + device + "'\n option data_interface 'customwan'\n");
}
for (let value in ['0.5', '1.5', '', 'bad', '61']) {
	config(value, 'lo');
	run('ucode ' + lib + 'refresh-config');
	check(trim(run('uci -q get unisoc_modem.main.home_refresh_interval')) == '2', 'migrate ' + value);
	check(trim(run('uci -q get unisoc_modem.main.data_interface')) == 'customwan', 'keep adapter');
}
for (let value in ['2', '2.5', '10', '60']) {
	config(value, 'lo');
	run('ucode ' + lib + 'refresh-config');
	check(trim(run('uci -q get unisoc_modem.main.home_refresh_interval')) == value, 'retain ' + value);
}
const sample = json(run('ucode ' + lib + 'dashboard-rates'));
check(sample.available && sample.device == 'lo' && sample.ifindex == 1, 'configured device');
check(sample.rx >= 0 && sample.tx >= 0 && sample.ts > 0 && length(sample.boot_id) > 0, 'counter types');
config('2', '../etc/passwd');
check(!json(run('ucode ' + lib + 'dashboard-rates')).available, 'reject path traversal');
config('2', 'missing0');
check(!json(run('ucode ' + lib + 'dashboard-rates')).available, 'missing interface');
printf('dashboard backend: %d checks passed\n', checks);
