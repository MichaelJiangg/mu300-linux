// Read-only nl80211 capability lookup. No PHY reset, interface or UCI writes.
import * as fs from 'fs';
import * as ubus from 'ubus';

export function parse(text) {
    let section = false, suites = [];
    for (let line in split(text || '', '\n')) {
        if (trim(line) == 'Supported Ciphers:') { section = true; continue; }
        if (!section) continue;
        if (!match(trim(line), /^\*/)) break;
        let m = match(line, /\(([0-9a-fA-F]{2}-[0-9a-fA-F]{2}-[0-9a-fA-F]{2}):([0-9]+)\)/);
        if (m) push(suites, lc(m[1]) + ':' + m[2]);
    }
    return suites;
};

export function capabilities(radio) {
    if (type(radio) != 'string' || !match(radio, /^[a-zA-Z0-9_]{1,64}$/)) return {};
    let bus = ubus.connect(null, 2);
    if (!bus) return {};
    let found;
    try { found = bus.call('iwinfo', 'phyname', {section:radio}); } catch (e) {}
    bus.disconnect();
    if (type(found?.phyname) != 'string' || !match(found.phyname, /^phy[0-9]+$/)) return {};
    let pipe = fs.popen('/opt/mu300/bin/busybox timeout 3 /usr/sbin/iw phy ' + found.phyname + ' info', 'r');
    if (!pipe) return {};
    let text = pipe.read('all'), code = pipe.close();
    if (code != 0) return {};
    let suites = parse(text);
    return length(suites) ? {phy:found.phyname, suites} : {};
};
