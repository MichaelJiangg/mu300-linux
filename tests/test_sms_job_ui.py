"""Exercise the actual LuCI view's asynchronous SMS job handling without a browser."""
import subprocess
import unittest

from helpers import TOP


class SmsJobUI(unittest.TestCase):
    def test_job_polling_and_duplicate_protection(self):
        source = TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/sms.js'
        code = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
let timers = [], slot = '1', replies = [], slots = [], notes = [], sends = 0;
let button = { isConnected: true }, draft = { value: 'test' };
const M = {
    selectedSlot: () => slot,
    callSmsJob: async (s) => { slots.push(s); return replies.shift(); },
    callSmsSend: async () => { sends++; return { ok: 1, job: 1 }; },
    busy: (b, value) => { b.busy = value; }, translate: x => x
};
const view = vm.runInNewContext('(function(){' + fs.readFileSync(process.argv[1], 'utf8') + '})()', {
    view: { extend: o => o }, M, Promise, Date,
    L: { resolveDefault: p => p.catch(() => null), bind: (f, obj) => f.bind(obj) },
    setTimeout: f => { timers.push(f); }
});
view.Q = id => id === 'sms-send' ? button : id === 'sms-num' ? { value: '10010' } : draft;
view.note = (text, kind) => { notes.push([text, kind]); };
view.reload = () => {};
const flush = async () => { for (let i=0; i<8; i++) await Promise.resolve(); };
(async () => {
    // A reload resumes an active SIM2 job, and fixes its slot for the entire poll.
    replies = [{ running: 1 }, { done: 1, ok: 1 }];
    view.watchJob(true); await flush();
    assert(button.busy); assert.strictEqual(view._jobWatch, true);
    view.send(); assert.strictEqual(sends, 0);
    slot = '0'; timers.shift()(); await flush();
    assert.deepStrictEqual(slots, ['1', '1']);
    assert.strictEqual(view._jobWatch, false); assert(!button.busy);
    assert(notes.some(n => n[1] === 'success'));
    // An old completed job is not announced again on page reload.
    notes = []; timers = []; replies = [{ done: 1, ok: 1 }];
    view.watchJob(true); await flush(); assert.strictEqual(notes.length, 0);
    // Double Enter/click is not a second submission.
    replies = [{ running: 1 }, { done: 1, ok: 0, error: 'refused' }];
    draft.value = 'test'; view.send(); view.send(); await flush();
    assert.strictEqual(sends, 1);
    timers.shift()(); await flush(); assert(!button.busy);
    assert.strictEqual(draft.value, 'test'); // failure preserves the draft
    // An uncertain outcome stops, never retries the send automatically.
    notes = []; replies = [null]; view.watchJob(false); await flush();
    assert.strictEqual(sends, 1); assert(!button.busy);
    assert(notes.some(n => n[1] === 'error'));
    // Navigation stops polling, including an outstanding callback.
    replies = [{ running: 1 }]; view.watchJob(false); await flush();
    button.isConnected = false; timers.shift()(); await flush();
    assert.strictEqual(view._jobWatch, false); assert(!button.busy);
    console.log('SMS view: resume, slot isolation, dedupe, uncertainty and navigation OK');
})().catch(e => { console.error(e); process.exitCode = 1; });
'''
        result = subprocess.run(['node', '-e', code, str(source)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
