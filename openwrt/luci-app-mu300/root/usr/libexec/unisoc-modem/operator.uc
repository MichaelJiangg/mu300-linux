// Parse a combined read-only CSCS/COPS reply. Never guess the encoding of a
// plain hexadecimal-looking name or confuse numeric PLMN with UCS2 text.
const reply = ARGV[0] || '';
const cops = match(reply, /\+COPS: *([0-9]+), *([0-9]+), *"([^"]*)"(, *([0-9]+))?/);
if (!cops) {
    print('null\n');
    exit(0);
}
let name = cops[3] || null;
const charset = match(reply, /\+CSCS: *"([^"]*)"/);
if (name && (cops[2] == '0' || cops[2] == '1') && charset && uc(charset[1]) == 'UCS2' && match(name, /^([0-9A-Fa-f]{4})+$/)) {
    let encoded = '"', valid = true, high = false;
    for (let i = 0; i < length(name); i += 4) {
        let unit = uc(substr(name, i, 4));
        let low = !!match(unit, /^D[CDEF]/);
        if (high != low || match(unit, /^00([01][0-9A-F]|7F|[89][0-9A-F])$/)) { valid = false; break; }
        high = !!match(unit, /^D[89AB]/);
        encoded += '\\u' + unit;
    }
    if (valid && !high) {
        try { name = json(encoded + '"'); } catch (e) { /* keep original */ }
    }
}
const numeric = cops[2] == '2';
printf('%J\n', {name: numeric ? null : name, plmn: numeric ? name : null, act: cops[5] != null ? int(cops[5]) : null});
