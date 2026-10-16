// E5-compatible placeholders, adapted to MU300's pinned HTTPS transport.
// This helper only validates/renders data. It never runs commands or sends mail.
import { readfile } from 'fs';
function fail() { print('{"ok":0}\n'); exit(1); }
function urlenc(s) {
    let out = '';
    for (let i = 0; i < length(s); i++) {
        let c = substr(s, i, 1);
        out += match(c, /[A-Za-z0-9_.~-]/) ? c : sprintf('%%%02X', ord(s, i));
    }
    return out;
}
function fill(s, values, encode) {
    return replace(s, /\{(from|text|time|sim|device|kind)\}/g,
        (all, key) => encode(`${values[key] ?? ''}`));
}
function walk(value, values) {
    if (type(value) == 'string') return fill(value, values, (s) => s);
    if (type(value) == 'array') return map(value, (v) => walk(v, values));
    if (type(value) == 'object') {
        let out = {};
        for (let k, v in value) out[k] = walk(v, values);
        return out;
    }
    return value;
}
try {
    let input = json(readfile('/dev/stdin')), c = input.config, v = input.values ?? {};
    if (type(c) != 'object') fail();
    let method = c.webhook_method ?? 'POST';
    let ct = c.webhook_content_type ?? 'application/json';
    let body = c.webhook_body ?? '', headers = c.webhook_headers ?? '';
    let timeout = c.webhook_timeout ?? 12, url = c.webhook_url ?? '';
    if (type(body) != 'string' || length(body) > 8192 ||
        type(headers) != 'string' || length(headers) > 4096 ||
        (method != 'GET' && method != 'POST') ||
        index(['application/json', 'application/x-www-form-urlencoded', 'text/plain'], ct) < 0 ||
        !match(`${timeout}`, /^[0-9]+$/) || +timeout < 1 || +timeout > 120) fail();
    // Placeholders may appear in path/query, never the TLS/DNS authority.
    let authority = match(url, /^https:\/\/([^\/?#]+)/);
    if (url && (!authority || match(authority[1], /[{}@]/) || match(url, /[[:space:][:cntrl:]#]/))) fail();
    let hs = [];
    for (let h in split(headers, '\n')) {
        if (!length(h)) continue;
        if (length(hs) >= 16 || !match(h, /^[A-Za-z0-9!#$%&'*+.^_`|~-]+:[^[:cntrl:]]+$/)) fail();
        let name = lc(split(h, ':')[0]);
        if (index(['host', 'content-length', 'content-type', 'transfer-encoding', 'connection', 'expect'], name) >= 0) fail();
        push(hs, h);
    }
    let rendered = body;
    if (length(body)) {
        if (ct == 'application/json') rendered = sprintf('%J', walk(json(body), v));
        else rendered = fill(body, v, ct == 'application/x-www-form-urlencoded' ? urlenc : (s) => s);
    }
    print(sprintf('%J\n', { ok: 1, url: fill(url, v, urlenc), body: rendered,
        method, content_type: ct, headers: join('\n', hs), timeout: +timeout }));
} catch (e) { fail(); }
