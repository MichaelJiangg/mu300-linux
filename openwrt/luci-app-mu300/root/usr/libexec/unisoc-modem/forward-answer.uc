/* PR #211: emit only a finite verdict, never any service response content. */
'use strict';
import * as fs from 'fs';
let rule = getenv('MU300_FORWARD_EXPECT') || '';
let valid = match(rule, /^[A-Za-z_][A-Za-z0-9_]{0,63}=(-?[0-9]{1,16}|[a-z]{1,16})$/);
let verdict = 'none';
try {
    let raw = fs.readfile(ARGV[0]);
    if (valid && raw != null && length(raw) <= 4096) {
        let data = json(raw);
        let sep = index(rule, '=');
        let key = substr(rule, 0, sep), wanted = substr(rule, sep + 1);
        if (type(data) == 'object' && key in data) {
            let value = data[key];
            if (type(value) in ['string', 'int', 'double', 'bool'] || value == null)
                verdict = (type(value) == 'string' ? value : sprintf('%J', value)) == wanted ? 'ok' : 'differs';
        }
    }
} catch (e) {}
print(verdict, '\n');
