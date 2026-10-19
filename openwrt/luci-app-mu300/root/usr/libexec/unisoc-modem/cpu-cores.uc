// Explicit CPU hotplug requests only. No daemon, governor or radio changes.
import * as fs from 'fs';
const ROOT = getenv('UNISOC_CORES_SYS') || '/sys/devices/system/cpu';
const CONFIG = getenv('UNISOC_CORES_CONFIG') || '/etc/unisoc-cpu-cores.json';
const DEFAULTS = getenv('UNISOC_CORES_DEFAULTS') || '/run/unisoc-cpu-cores-defaults.json';
const ERROR = getenv('UNISOC_CORES_ERROR') || '/run/unisoc-cpu-cores-error';
function text(path) { return trim(fs.readfile(path) || ''); }
function cores() {
    let out = [], present = text(ROOT + '/present');
    for (let name in fs.lsdir(ROOT) || []) {
        if (!match(name, /^cpu[0-9]+$/)) continue;
        let id = int(substr(name, 3)), path = ROOT + '/' + name + '/online';
        if (length(present) && !length(filter(split(present, ','), range => {
            let pair = split(range, '-');
            return length(pair) == 1 ? id == int(pair[0]) : id >= int(pair[0]) && id <= int(pair[1]);
        }))) continue;
        let value = text(path), valid = value == '0' || value == '1';
        // A missing online file denotes a kernel-managed, non-hotpluggable CPU.
        push(out, {id, online: valid ? value == '1' : true,
            writable: id != 0 && valid && !!(fs.stat(path)?.mode & 128)});
    }
    return sort(out, (a, b) => a.id - b.id);
}
function settings(current) { return map(current, c => ({id:c.id, online:c.online})); }
function store(path, value) {
    let data = sprintf('%J\n', value), tmp = path + '.new';
    if (fs.writefile(tmp, data) == length(data) && fs.chmod(tmp, 384) && fs.rename(tmp, path)) return true;
    fs.unlink(tmp);
    return false;
}
function state() {
    return {ok:1, cores:cores(), persistent:!!fs.stat(CONFIG), boot_error:text(ERROR)};
}
function validate(target, current) {
    if (type(target) != 'array' || length(target) != length(current) || !length(current))
        die('cpu_cores_invalid');
    let seen = {};
    for (let c in target) {
        if (type(c) != 'object' || length(keys(c)) != 2 || type(c.id) != 'int' || type(c.online) != 'bool')
            die('cpu_cores_invalid');
        let found = filter(current, p => p.id == c.id)[0];
        if (!found || seen[''+c.id]) die('cpu_cores_topology');
        seen[''+c.id] = true;
        if ((c.id == 0 && !c.online) || (!found.writable && c.online != found.online))
            die('cpu_cores_fixed');
    }
    if (!length(filter(target, c => c.online))) die('cpu_cores_fixed');
    return sort(target, (a, b) => a.id - b.id);
}
function write(c) {
    let path = ROOT + '/cpu' + c.id + '/online', value = c.online ? '1' : '0';
    if (text(path) == value) return true;
    // CPU hotplug sysfs writes are synchronous; do not retry a rejected write.
    return fs.writefile(path, value + '\n') == 2 && text(path) == value;
}
function apply(input, replay) {
    let current = cores();
    if (type(input) != 'object' || type(input.persist) != 'bool' ||
        length(filter(keys(input), k => k != 'cores' && k != 'persist' && k != 'reset')) ||
        (input.reset != null && type(input.reset) != 'bool')) die('cpu_cores_invalid');
    let base = fs.stat(DEFAULTS) ? json(fs.readfile(DEFAULTS)) : null;
    let target = input.reset === true ? base?.cores || settings(current) : input.cores;
    target = validate(target, current);
    if (!base && !store(DEFAULTS, {version:1, cores:settings(current)})) die('cpu_cores_save');
    let changed = [], error = null;
    // Bring requested cores online before offlining any others.
    for (let online in [true, false]) for (let c in target) {
        let old = filter(current, p => p.id == c.id)[0];
        if (error || c.online != online || c.online == old.online) continue;
        push(changed, {id:old.id, online:old.online});
        if (!write(c)) { error = 'cpu_cores_write'; break; }
    }
    // Also detect a concurrent platform hotplug policy changing the result.
    if (!error) {
        let actual = cores();
        if (length(actual) != length(target) || length(filter(target, c =>
            !length(filter(actual, a => a.id == c.id && a.online == c.online))))) error = 'cpu_cores_write';
    }
    if (!error && !replay) {
        if (input.persist && input.reset !== true) {
            if (!store(CONFIG, {version:1, cores:target})) error = 'cpu_cores_save';
        } else if (fs.stat(CONFIG) && !fs.unlink(CONFIG)) error = 'cpu_cores_save';
    }
    if (error) {
        let rollback = true;
        for (let online in [true, false]) for (let c in changed)
            if (c.online == online && !write(c)) rollback = false;
        return {ok:0, error, rollback, cores:cores()};
    }
    fs.unlink(ERROR);
    return state();
}
let action = ARGV[0] || 'get', result;
try {
    if (action == 'get') result = state();
    else if (action == 'apply') {
        let file = fs.open('/dev/stdin', 'r'), raw = file?.read(32769);
        file?.close();
        if (raw == null || length(raw) > 32768) die('cpu_cores_invalid');
        let input = json(raw);
        // rpcd adds this transport field to authenticated HTTP ubus calls.
        // Keep it outside the settings schema and never persist the token.
        if (type(input) == 'object') delete input.ubus_rpc_session;
        result = apply(input, false);
    } else if (action == 'boot') {
        if (!fs.stat(CONFIG)) result = {ok:1, skipped:true};
        else {
            let profile = json(fs.readfile(CONFIG));
            if (type(profile?.version) != 'int' || profile.version != 1 || length(keys(profile)) != 2) die('cpu_cores_invalid');
            result = apply({cores:profile.cores, persist:true}, true);
        }
    } else die('cpu_cores_invalid');
} catch (e) {
    let message = trim(e.message || ''+e);
    result = {ok:0, error: match(message, /^cpu_cores_(invalid|topology|fixed|save)$/) ? message : 'cpu_cores_invalid'};
}
if (action == 'boot' && !result.ok) fs.writefile(ERROR, result.error + '\n');
printf('%J\n', result);
exit(result.ok ? 0 : 1);
