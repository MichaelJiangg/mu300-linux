// Run only in a disposable OpenWrt container with MU300_TEST_CONTAINER=1.
// ucode /src/tests/dashboard_rates.uc /src
import { readfile, writefile, mkdir, popen } from 'fs';
if (getenv('MU300_TEST_CONTAINER') != '1') die('Disposable container required\n');
const repo = ARGV[0] || '/src';
const pipe = popen('mktemp -d /tmp/mu300-rate-test.XXXXXX', 'r');
const dir = trim(pipe.read('all')); pipe.close();
let checks = 0;
function check(ok, label) { if (!ok) die('FAIL: ' + label + '\n'); checks++; }
check(match(dir, /^\/tmp\/mu300-rate-test\.[A-Za-z0-9]+$/), 'private fixture');
mkdir('/etc/config');
mkdir(dir + '/net');
for (let device, index in { sipa_eth0: 1, sipa_eth3: 4, sipa_eth11: 12 }) {
	mkdir(dir + '/net/' + device);
	mkdir(dir + '/net/' + device + '/statistics');
	writefile(dir + '/net/' + device + '/ifindex', '' + index);
	writefile(dir + '/net/' + device + '/statistics/rx_bytes', '' + index * 100);
	writefile(dir + '/net/' + device + '/statistics/tx_bytes', '' + index * 200);
}
// Only the transport and sysfs root are substituted. Execute the actual
// counter reader, real UCI parser, and its WAN/config selection logic.
const fixture = sprintf('%J', dir);
writefile(dir + '/rates-test-ubus.uc',
	"import { readfile, writefile } from 'fs';\n" +
	"export function connect(path, timeout) {\n" +
	" const dir=" + fixture + ";\n" +
	" const reply=readfile(dir+'/wan.json');\n" +
	" if(reply=='connect-error')die('fixture connection failure');\n" +
	" return {call:(object,method,args)=>{\n" +
	"  writefile(dir+'/call.json',sprintf('%J',{object,method,timeout}));\n" +
	"  if(reply=='call-error')die('fixture RPC failure');\n" +
	"  return json(reply);\n" +
	" }};\n};\n");
let source = readfile(repo + '/openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/dashboard-rates');
source = replace(source, "from 'ubus'", "from './rates-test-ubus.uc'");
source = replace(source, "'/sys/class/net/'", sprintf('%J', dir + '/net/'));
writefile(dir + '/rates.uc', source);
function sample(wan, configured) {
	writefile('/etc/config/unisoc_modem', "config core 'main'\n option data_interface 'customwan'\n" +
		(configured == null ? '' : " option data_device '" + configured + "'\n"));
	writefile(dir + '/wan.json', type(wan) == 'string' ? wan : sprintf('%J', wan));
	const p = popen('ucode ' + dir + '/rates.uc', 'r');
	const output = p.read('all');
	check(p.close() == 0, 'counter reader returned successfully');
	return json(output);
}
let s = sample({l3_device:'sipa_eth3',device:'sipa_eth0'}, 'sipa_eth0');
check(s.available && s.device == 'sipa_eth3' && s.rx == 400, 'live WAN overrides stale configured port');
const request = json(readfile(dir + '/call.json'));
check(request.object == 'network.interface.customwan' && request.method == 'status' && request.timeout == 1,
	'one bounded status request on the configured interface');
writefile(dir + '/net/sipa_eth3/statistics/rx_bytes', '900');
let next = sample({l3_device:'sipa_eth3'}, 'sipa_eth0');
check(next.rx - s.rx == 500, 'counter growth follows active port');
next = sample({device:'sipa_eth11'}, 'sipa_eth0');
check(next.device == 'sipa_eth11' && next.ifindex == 12 && next.rx == 1200, 'SIM2 device fallback and changed rate identity');
for (let reply in [{}, null, 'connect-error', 'call-error']) {
	s = sample(reply, 'sipa_eth3');
	check(s.available && s.device == 'sipa_eth3', 'configured fallback when WAN is unavailable');
}
s = sample({}, null);
check(s.available && s.device == 'sipa_eth0', 'default port without WAN or configured device');
s = sample({l3_device:'../etc/passwd'}, 'sipa_eth0');
check(!s.available, 'reject unsafe live device');
s = sample({}, '../etc/passwd');
check(!s.available, 'reject unsafe fallback');
s = sample({l3_device:'missing0'}, 'sipa_eth0');
check(!s.available, 'do not invent counters for missing live interface');
printf('dashboard rates: %d checks passed\n', checks);
