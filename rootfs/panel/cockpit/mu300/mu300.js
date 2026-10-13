/* The MU300 page of Cockpit (Ubuntu): the device's own tools on one page. Every command is run by cockpit.spawn with
 * an argument array (never a shell, so nothing typed here is ever parsed as a command line), with Cockpit's
 * administrative access where the tool needs root ("try": without it the page says what needs it). Secrets (the
 * hotspot and Wi-Fi passwords) go on stdin, never into an argument. Every value from a command is put in as text
 * (textContent), never as HTML. Translations: po.<lang>.js (cockpit.locale), English is the source. */
/* global cockpit */
(function () {
    'use strict';
    var _ = cockpit.gettext;

    /* ---- small helpers ---------------------------------------------------------------------------------- */
    function el(tag, attrs, children) {
        var e = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === 'class') e.className = attrs[k];
            else if (k === 'text') e.textContent = attrs[k];
            else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2), attrs[k]);
            else e.setAttribute(k, attrs[k]);
        });
        (children || []).forEach(function (c) {
            if (c === null || c === undefined) return;
            e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        });
        return e;
    }
    function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }
    function card(title, id) { return el('section', { 'class': 'mu-card', id: id }, [ el('h2', { text: title }) ]); }
    function row(label, value) {
        return el('div', { 'class': 'mu-row' }, [ el('span', { 'class': 'mu-k', text: label }),
            el('span', { 'class': 'mu-v', text: value === null || value === undefined || value === '' ? '-' : String(value) }) ]);
    }
    function note(text, kind) { return el('p', { 'class': 'mu-note' + (kind ? ' mu-' + kind : ''), text: text }); }
    function button(text, onclick, kind) {
        return el('button', { 'class': 'mu-btn' + (kind ? ' mu-' + kind : ''), type: 'button', onclick: onclick, text: text });
    }
    function pre(text) { return el('pre', { 'class': 'mu-pre', text: text }); }

    /* the error of a command, worded */
    function errText(ex) {
        if (!ex) return _('Unknown error');
        if (ex.problem === 'not-found') return _('The command is not on this system.');
        if (ex.problem === 'access-denied' || ex.problem === 'authentication-failed')
            return _('This needs administrative access: turn it on at the top of Cockpit.');
        return String(ex.message || ex.problem || ex);
    }
    /* cmd(argv[, input]): the output, root where Cockpit has administrative access */
    function cmd(argv, input) {
        var p = cockpit.spawn(argv, { superuser: 'try', err: 'message' });
        if (input !== undefined) p.input(input);
        return p;
    }
    function cmdJson(argv) {
        return cmd(argv).then(function (out) { return JSON.parse(out); });
    }
    function busy(btn, on) { if (btn) { btn.disabled = !!on; btn.classList.toggle('mu-busy', !!on); } }
    function act(btn, argv, input, done) {
        busy(btn, true);
        return cmd(argv, input).then(function (out) {
            busy(btn, false);
            toast(out.trim() || _('Done'), 'ok');
            if (done) done();
        }, function (ex) {
            busy(btn, false);
            toast(errText(ex), 'error');
        });
    }
    function toast(text, kind) {
        var box = document.getElementById('mu-toast');
        clear(box).appendChild(el('div', { 'class': 'mu-toast mu-' + (kind || 'ok'), text: text }));
        clearTimeout(toast.t);
        toast.t = setTimeout(function () { clear(box); }, 6000);
    }

    function fmtBytes(n) {
        n = Number(n);
        if (!isFinite(n) || n < 0) return '-';
        var u = [ 'B', 'KiB', 'MiB', 'GiB', 'TiB' ], i = 0;
        while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
        return (i ? n.toFixed(1) : String(Math.round(n))) + ' ' + u[i];
    }
    function fmtRate(bps) {
        if (!isFinite(bps) || bps < 0) return '-';
        var bits = bps * 8, u = [ 'bit/s', 'kbit/s', 'Mbit/s', 'Gbit/s' ], i = 0;
        while (bits >= 1000 && i < u.length - 1) { bits /= 1000; i++; }
        return (i ? bits.toFixed(1) : String(Math.round(bits))) + ' ' + u[i];
    }
    /* /proc/net/dev: {iface: {rx, tx}} */
    function netDev(text) {
        var out = {};
        String(text || '').split('\n').forEach(function (line) {
            var m = line.match(/^\s*([^:\s]+):\s*(.*)$/);
            if (!m) return;
            var f = m[2].trim().split(/\s+/);
            if (f.length >= 9) out[m[1]] = { rx: Number(f[0]), tx: Number(f[8]) };
        });
        return out;
    }

    /* ---- the pages -------------------------------------------------------------------------------------- */
    var pages = {}, current = null, timers = [];
    function every(ms, fn) { fn(); timers.push(setInterval(fn, ms)); }
    function stopTimers() { timers.forEach(clearInterval); timers = []; }

    /* Overview: the device in one call (mu300-panel info), data usage (mu300-traffic json), the live rates from
     * /proc/net/dev every 2 s (read in the browser's session, no process, no root) */
    pages.overview = function (root) {
        var sig = card(_('Mobile network'), 'mu-signal'), data = card(_('Mobile data'), 'mu-data');
        var usage = card(_('Data usage'), 'mu-usage'), rates = card(_('Live rates'), 'mu-rates');
        var dev = card(_('Device'), 'mu-device');
        root.appendChild(el('div', { 'class': 'mu-grid' }, [ sig, data, rates, usage, dev ]));
        var sigBody = sig.appendChild(el('div')), dataBody = data.appendChild(el('div'));
        var usageBody = usage.appendChild(el('div')), rateBody = rates.appendChild(el('div'));
        var devBody = dev.appendChild(el('div'));

        function paint(info) {
            var s = info.signal || {};
            var regs = { home: _('Registered (home network)'), roaming: _('Registered (roaming)'),
                searching: _('Searching'), denied: _('Registration denied'), none: _('Not registered'),
                emergency: _('Emergency calls only') };
            clear(sigBody).appendChild(row(_('Operator'), s.operator));
            sigBody.appendChild(row(_('Technology'), s.rat));
            sigBody.appendChild(row(_('Registration'), regs[s.registration] || s.registration));
            sigBody.appendChild(row(_('RSRP'), s.rsrp === null || s.rsrp === undefined ? null : s.rsrp + ' dBm'));
            sigBody.appendChild(row(_('RSRQ'), s.rsrq === null || s.rsrq === undefined ? null : s.rsrq + ' dB'));
            if (!info.signal) sigBody.appendChild(note(_('No readings from the modem (mu300-at).')));

            var md = info.mobile_data || {}, on = md.service === 'active';
            clear(dataBody).appendChild(row(_('State'), on ? _('On') : _('Off')));
            dataBody.appendChild(row(_('Address'), md.address));
            var b = button(on ? _('Turn mobile data off') : _('Turn mobile data on'), function () {
                if (on && !window.confirm(_('Turn mobile data off? Clients of the device lose the internet until it is on again.'))) return;
                act(b, [ 'systemctl', on ? 'stop' : 'start', 'mu300-mobile-data' ], undefined, refresh);
            });
            dataBody.appendChild(b);

            clear(devBody).appendChild(row(_('Device'), { f50: 'ZTE F50', u30air: 'ZTE U30 Air' }[info.device] || info.device));
            devBody.appendChild(row(_('Release'), info.version));
            if (info.battery) {
                var bt = info.battery;
                devBody.appendChild(row(_('Battery'), (bt.capacity === null ? '-' : bt.capacity + ' %') +
                    (bt.status ? ' (' + bt.status + ')' : '')));
            }
            var temps = (info.temperatures || []).filter(function (t) { return t.millicelsius > 0; });
            if (temps.length) {
                var max = temps.reduce(function (a, t) { return t.millicelsius > a.millicelsius ? t : a; });
                devBody.appendChild(row(_('Hottest sensor'), (max.millicelsius / 1000).toFixed(1) + ' °C (' + max.name + ')'));
            }
            if (info.cpu && info.cpu.profile) devBody.appendChild(row(_('CPU profile'), profileName(info.cpu.profile)));
            if (info.hotspot && info.hotspot.ssid) devBody.appendChild(row(_('Hotspot'), info.hotspot.ssid));
            devBody.appendChild(note(_('Network, band and cell locks are part of the OpenWrt control panel (openwrt-luci); on Ubuntu, AT commands go through mu300-at in the Terminal.')));
        }
        function refresh() {
            return cmdJson([ 'mu300-panel', 'info' ]).then(paint, function (ex) {
                clear(sigBody).appendChild(note(errText(ex), 'error'));
            });
        }
        function usageRefresh() {
            return cmdJson([ 'mu300-traffic', 'json' ]).then(function (t) {
                clear(usageBody);
                if (t.today) usageBody.appendChild(row(_('Today'), fmtBytes(Number(t.today.rx) + Number(t.today.tx))));
                if (t.cycle) {
                    usageBody.appendChild(row(_('This billing cycle'), fmtBytes(t.cycle.used)));
                    usageBody.appendChild(row(_('Cycle'), t.cycle.start + ' - ' + t.cycle.last));
                }
                if (t.cap && t.cap.bytes) usageBody.appendChild(row(_('Monthly cap'), fmtBytes(t.cap.bytes)));
            }, function (ex) { clear(usageBody).appendChild(note(errText(ex), 'error')); });
        }
        var last = null;
        function rateRefresh() {
            return cockpit.file('/proc/net/dev').read().then(function (text) {
                var now = { t: Date.now(), dev: netDev(text) };
                clear(rateBody);
                var known = [ [ 'sipa_eth0', _('Mobile data') ], [ 'br-lan', _('LAN') ], [ 'wlan0', _('Wi-Fi') ] ];
                /* none of them (yet): every other interface that carried anything, but the loopback */
                if (!known.some(function (p) { return now.dev[p[0]]; }))
                    known = Object.keys(now.dev).filter(function (n) {
                        return n !== 'lo' && now.dev[n].rx + now.dev[n].tx > 0;
                    }).map(function (n) { return [ n, n ]; });
                known.forEach(function (p) {
                    var a = last && last.dev[p[0]], c = now.dev[p[0]];
                    if (!c) return;
                    var dt = last ? (now.t - last.t) / 1000 : 0;
                    var down = a && dt > 0 ? Math.max(0, (c.rx - a.rx) / dt) : NaN;
                    var up = a && dt > 0 ? Math.max(0, (c.tx - a.tx) / dt) : NaN;
                    rateBody.appendChild(row(p[1], '↓ ' + fmtRate(down) + '   ↑ ' + fmtRate(up)));
                });
                last = now;
            }, function () {});
        }
        every(10000, refresh);
        every(60000, usageRefresh);
        every(2000, rateRefresh);
    };

    function profileName(p) {
        return { saving: _('Power saving'), balanced: _('Balanced'), performance: _('Performance') }[p] || p;
    }

    /* SMS: sms json (the reassembled messages of the SIM), sms send, sms delete per index */
    pages.sms = function (root) {
        var list = card(_('Messages'), 'mu-sms-list'), send = card(_('Send a message'), 'mu-sms-send');
        root.appendChild(send);
        root.appendChild(list);
        var body = list.appendChild(el('div'));
        var num = el('input', { type: 'tel', id: 'mu-sms-number', placeholder: '+90...', maxlength: '21' });
        var text = el('textarea', { id: 'mu-sms-text', rows: '3', maxlength: '1000' });
        var sb = button(_('Send'), function () {
            var n = num.value.trim(), t = text.value;
            if (!/^\+?[0-9]{3,20}$/.test(n)) { toast(_('Enter a phone number (digits, an optional + first).'), 'error'); return; }
            if (!t.trim()) { toast(_('The message is empty.'), 'error'); return; }
            act(sb, [ 'sms', 'send', n, t ], undefined, function () { text.value = ''; });
        }, 'primary');
        send.appendChild(el('label', { 'for': 'mu-sms-number', text: _('Number') }));
        send.appendChild(num);
        send.appendChild(el('label', { 'for': 'mu-sms-text', text: _('Text') }));
        send.appendChild(text);
        send.appendChild(sb);
        var rb = button(_('Refresh'), function () { load(); });
        list.insertBefore(rb, body);

        function load() {
            clear(body).appendChild(note(_('Reading the SIM...')));
            busy(rb, true);
            return cmdJson([ 'sms', 'json' ]).then(function (r) {
                busy(rb, false);
                clear(body);
                var msgs = (r && r.messages) || [];
                if (!msgs.length) { body.appendChild(note(_('No messages.'))); return; }
                msgs.slice().reverse().forEach(function (m) {
                    var idx = (m.index || []).filter(function (i) { return /^[0-9]{1,4}$/.test(String(i)); });
                    var del = button(_('Delete'), function () {
                        if (!window.confirm(_('Delete this message from the SIM?'))) return;
                        busy(del, true);
                        idx.reduce(function (p, i) { return p.then(function () { return cmd([ 'sms', 'delete', String(i) ]); }); },
                            Promise.resolve()).then(load, function (ex) { busy(del, false); toast(errText(ex), 'error'); });
                    }, 'danger');
                    var head = m.sender + '  ' + m.time + (m.parts > 1 ? '  (' + cockpit.format(_('$0 parts'), m.parts) + ')' : '');
                    body.appendChild(el('div', { 'class': 'mu-msg' }, [ el('div', { 'class': 'mu-msg-head', text: head }),
                        el('div', { 'class': 'mu-msg-text', text: m.text }), del ]));
                });
            }, function (ex) {
                busy(rb, false);
                /* an older system's sms has no json: its list as text */
                if (ex && ex.exit_status === 2)
                    return cmd([ 'sms', 'list' ]).then(function (out) {
                        clear(body).appendChild(pre(out.replace(/\x1b\[[0-9;]*m/g, '')));
                    });
                clear(body).appendChild(note(errText(ex), 'error'));
            });
        }
        load();
    };

    /* VPN: mu300-vpn's JSON (the VPN module, mu300-extra install vpn) */
    pages.vpn = function (root) {
        var st = card(_('VPN'), 'mu-vpn'), pr = card(_('Profiles'), 'mu-vpn-profiles');
        root.appendChild(st);
        root.appendChild(pr);
        var sb = st.appendChild(el('div')), pb = pr.appendChild(el('div'));
        function load() {
            return cmdJson([ 'mu300-vpn', 'status', '--json' ]).then(function (s) {
                clear(sb);
                sb.appendChild(row(_('Switch'), s.enabled ? _('On') : _('Off')));
                sb.appendChild(row(_('Running'), s.running ? _('Yes') : _('No')));
                sb.appendChild(row(_('Profile'), s.profile ? s.profile.name + ' (' + s.profile.type + ')' : null));
                sb.appendChild(row(_('Tunnel'), s.tunnel && s.tunnel.up ? (s.tunnel.iface || '') + ' ' + _('up') : _('down')));
                sb.appendChild(row(_('Kill switch'), s.kill_switch && s.kill_switch.active ? _('active') : _('inactive')));
                if (s.missing_engine) sb.appendChild(note(cockpit.format(_('The profile needs the engine extra $0: sudo mu300-extra install $0'), s.missing_engine), 'warn'));
                var b = button(s.enabled ? _('Turn the VPN off') : _('Turn the VPN on'), function () {
                    act(b, [ 'mu300-vpn', s.enabled ? 'off' : 'on' ], undefined, load);
                }, s.enabled ? 'danger' : 'primary');
                sb.appendChild(b);
                return cmdJson([ 'mu300-vpn', 'profile', 'list', '--json' ]).then(function (list) {
                    clear(pb);
                    if (!list.length) { pb.appendChild(note(_('No profiles: add one with mu300-vpn profile import (Terminal) or mu300-toolkit.'))); return; }
                    list.forEach(function (p) {
                        var id = String(p.id || '');
                        if (!/^[a-z0-9-]{1,32}$/.test(id)) return;
                        var line = el('div', { 'class': 'mu-row' }, [ el('span', { 'class': 'mu-k', text: p.name + ' (' + p.type + ')' }) ]);
                        if (p.active) line.appendChild(el('span', { 'class': 'mu-v', text: _('active') }));
                        else {
                            var u = button(_('Use'), function () { act(u, [ 'mu300-vpn', 'profile', 'use', id ], undefined, load); });
                            line.appendChild(u);
                        }
                        pb.appendChild(line);
                    });
                });
            }, function (ex) {
                clear(sb);
                clear(pb);
                if (ex && ex.problem === 'not-found')
                    sb.appendChild(note(_('The VPN module is not installed: sudo mu300-extra install vpn')));
                else sb.appendChild(note(errText(ex), 'error'));
            });
        }
        load();
    };

    /* Power and CPU: mu300-cpu status --json and profile NAME, mu300-power status (text) */
    pages.power = function (root) {
        var cpu = card(_('CPU profile'), 'mu-cpu'), pw = card(_('Power'), 'mu-power');
        root.appendChild(cpu);
        root.appendChild(pw);
        var cb = cpu.appendChild(el('div')), pb = pw.appendChild(el('div'));
        function load() {
            cmdJson([ 'mu300-cpu', 'status', '--json' ]).then(function (s) {
                clear(cb);
                cb.appendChild(note(_('A profile sets the CPU governor and the per-cluster frequency limits, inside the hardware frequency table; the kernel keeps throttling at its thermal limit in every profile.')));
                var bar = el('div', { 'class': 'mu-actions' });
                (s.profiles || [ 'saving', 'balanced', 'performance' ]).forEach(function (p) {
                    if (!/^[a-z]{1,20}$/.test(p)) return;
                    var b = button(profileName(p), function () { act(b, [ 'mu300-cpu', 'profile', p ], undefined, load); },
                        p === s.profile ? 'primary' : '');
                    bar.appendChild(b);
                });
                cb.appendChild(bar);
                (s.policies || []).forEach(function (pol) {
                    /* mu300-cpu reports MHz */
                    var mhz = function (v) { return typeof v === 'number' ? v + ' MHz' : '-'; };
                    cb.appendChild(row('CPU ' + pol.cpus, pol.governor + ', ' + mhz(pol.cur) + ' (' + mhz(pol.min) + ' - ' + mhz(pol.max) + ')'));
                });
                if (s.throttling) cb.appendChild(note(_('Thermal throttling is active right now.'), 'warn'));
            }, function (ex) { clear(cb).appendChild(note(errText(ex), 'error')); });
            cmd([ 'mu300-power', 'status' ]).then(function (out) { clear(pb).appendChild(pre(out)); },
                function (ex) { clear(pb).appendChild(note(errText(ex), 'error')); });
        }
        load();
    };

    /* Wi-Fi: the hotspot's name and password (mu300-panel hotspot-set, the password on stdin), the client
     * (wifi-client status / connect SSID - with the password on stdin / disconnect) */
    pages.wifi = function (root) {
        var hs = card(_('Hotspot'), 'mu-hotspot'), cl = card(_('Join a Wi-Fi network'), 'mu-wifi-client');
        root.appendChild(hs);
        root.appendChild(cl);
        var ssid = el('input', { type: 'text', id: 'mu-hs-ssid', maxlength: '32' });
        var psk = el('input', { type: 'password', id: 'mu-hs-psk', maxlength: '63', autocomplete: 'new-password' });
        cmdJson([ 'mu300-panel', 'info' ]).then(function (i) { if (i.hotspot && i.hotspot.ssid) ssid.value = i.hotspot.ssid; }, function () {});
        var hb = button(_('Save and restart the hotspot'), function () {
            var s = ssid.value, p = psk.value;
            if (!s || new TextEncoder().encode(s).length > 32) { toast(_('The name must be 1 to 32 bytes.'), 'error'); return; }
            if (!/^[\x20-\x7e]{8,63}$/.test(p)) { toast(_('The password must be 8 to 63 printable ASCII characters.'), 'error'); return; }
            if (!window.confirm(_('Restart the hotspot? Devices on it are disconnected and must join again, with the new password.'))) return;
            act(hb, [ 'mu300-panel', 'hotspot-set', s ], p + '\n', function () { psk.value = ''; });
        }, 'primary');
        hs.appendChild(el('label', { 'for': 'mu-hs-ssid', text: _('Name (SSID)') }));
        hs.appendChild(ssid);
        hs.appendChild(el('label', { 'for': 'mu-hs-psk', text: _('New password') }));
        hs.appendChild(psk);
        hs.appendChild(hb);

        var cs = cl.appendChild(el('div'));
        cl.appendChild(note(_('The radio does one thing at a time: joining a network turns the hotspot off while it is joined. If you reach this page over the hotspot, you lose it.'), 'warn'));
        var cssid = el('input', { type: 'text', id: 'mu-wc-ssid', maxlength: '32' });
        var cpsk = el('input', { type: 'password', id: 'mu-wc-psk', maxlength: '63', autocomplete: 'off' });
        var jb = button(_('Join'), function () {
            var s = cssid.value;
            if (!s || new TextEncoder().encode(s).length > 32) { toast(_('The name must be 1 to 32 bytes.'), 'error'); return; }
            act(jb, cpsk.value ? [ 'wifi-client', 'connect', s, '-' ] : [ 'wifi-client', 'connect', s, '--open' ],
                cpsk.value ? cpsk.value + '\n' : undefined, function () { cpsk.value = ''; status(); });
        }, 'primary');
        var db = button(_('Leave and turn the hotspot back on'), function () {
            act(db, [ 'wifi-client', 'disconnect' ], undefined, status);
        });
        cl.appendChild(el('label', { 'for': 'mu-wc-ssid', text: _('Network name') }));
        cl.appendChild(cssid);
        cl.appendChild(el('label', { 'for': 'mu-wc-psk', text: _('Password (empty for an open network)') }));
        cl.appendChild(cpsk);
        cl.appendChild(el('div', { 'class': 'mu-actions' }, [ jb, db ]));
        function status() {
            cmd([ 'wifi-client', 'status' ]).then(function (out) { clear(cs).appendChild(pre(out)); },
                function (ex) { clear(cs).appendChild(note(errText(ex), 'error')); });
        }
        status();
    };

    /* Updates: mu300-update version / check, and apply after a confirmation, its output as it comes */
    pages.updates = function (root) {
        var c = card(_('Updates'), 'mu-updates');
        root.appendChild(c);
        var out = pre('');
        var cb = button(_('Check for updates'), function () {
            busy(cb, true);
            out.textContent = _('Checking...');
            cmd([ 'mu300-update', 'check' ]).then(function (o) { busy(cb, false); out.textContent = o; },
                function (ex) { busy(cb, false); out.textContent = errText(ex); });
        });
        var ab = button(_('Install the update'), function () {
            if (!window.confirm(_('Install the newest release now? The systems are replaced (your settings are kept) and the new one runs after the next reboot. Keep the device powered until it is done.'))) return;
            busy(ab, true);
            out.textContent = '';
            var p = cmd([ 'mu300-update', 'apply' ]);
            p.stream(function (data) { out.textContent += data; out.scrollTop = out.scrollHeight; });
            p.then(function () { busy(ab, false); toast(_('The update is installed: reboot to run it.'), 'ok'); },
                function (ex) { busy(ab, false); out.textContent += '\n' + errText(ex); });
        }, 'danger');
        c.appendChild(el('div', { 'class': 'mu-actions' }, [ cb, ab ]));
        c.appendChild(out);
        cmd([ 'mu300-update', 'version' ]).then(function (o) { if (!out.textContent) out.textContent = o; }, function () {});
    };

    /* ---- the frame ---------------------------------------------------------------------------------------- */
    var TABS = [ [ 'overview', _('Overview') ], [ 'sms', _('SMS') ], [ 'power', _('Power and CPU') ],
        [ 'wifi', _('Wi-Fi') ], [ 'updates', _('Updates') ] ];
    /* The VPN tab only when the VPN module is installed: its mu300-vpn in the vpn extra on the disk, the test
     * mu300-extra itself uses (vpn_module_in). Without the module the page says nothing of a VPN; the module is
     * installed with mu300-extra install vpn, and the tab is there at the next load. */
    var VPN_MODULE = '/mnt/mu300-disk/extra/vpn/bin/mu300-vpn';
    var vpnOn = false;
    function show(name) {
        if (!pages[name] || (name === 'vpn' && !vpnOn)) name = 'overview';
        stopTimers();
        current = name;
        Array.prototype.forEach.call(document.querySelectorAll('.mu-tab'), function (t) {
            t.classList.toggle('mu-active', t.getAttribute('data-tab') === name);
        });
        var main = clear(document.getElementById('mu-main'));
        pages[name](main);
        if (cockpit.location.path[0] !== name) cockpit.location.go([ name ]);
    }
    function tab(name, label) {
        return el('button', { 'class': 'mu-tab', type: 'button', 'data-tab': name, text: label,
            onclick: function () { show(name); } });
    }
    function start() {
        var app = document.getElementById('app');
        var nav = el('nav', { 'class': 'mu-tabs' });
        var tabs = {};
        TABS.forEach(function (t) { tabs[t[0]] = nav.appendChild(tab(t[0], t[1])); });
        app.appendChild(el('h1', { text: 'MU300' }));
        app.appendChild(nav);
        app.appendChild(el('div', { id: 'mu-toast' }));
        app.appendChild(el('main', { id: 'mu-main' }));
        cockpit.translate();
        var want = cockpit.location.path[0] || 'overview';
        /* a cheap check (no shell): with the module, the tab goes in before Power and the tab asked for is shown */
        var vpn = cmd([ 'test', '-x', VPN_MODULE ]).then(function () {
            vpnOn = true;
            nav.insertBefore(tab('vpn', _('VPN')), tabs.power);
        }, function () {});
        if (want === 'vpn') vpn.then(function () { show(want); });
        else show(want);
        cockpit.addEventListener('locationchanged', function () {
            if (cockpit.location.path[0] !== current) show(cockpit.location.path[0]);
        });
    }
    /* for the tests: the helpers, without a page */
    window.MU300 = { netDev: netDev, fmtBytes: fmtBytes, fmtRate: fmtRate, errText: errText, pages: pages, show: show };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
}());
