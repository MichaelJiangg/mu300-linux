'use strict';
const fs = require('fs'), assert = require('assert');
const file = process.argv[2];
let now = 0, seq = 0;
const timers = new Map(), listeners = new Set();
const document = { hidden: false,
    addEventListener: (name, fn) => listeners.add(fn),
    removeEventListener: (name, fn) => listeners.delete(fn) };
const timeout = (fn, delay) => { const id = ++seq; timers.set(id, { fn, at: now + delay }); return id; };
const clear = id => timers.delete(id);
const R = new Function('baseclass', 'document', 'performance', 'setTimeout', 'clearTimeout', fs.readFileSync(file, 'utf8'))(
    { extend: obj => obj }, document, { now: () => now }, timeout, clear);
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
async function advance(ms) {
    const end = now + ms;
    for (;;) {
        const next = [...timers].filter(([,t]) => t.at <= end).sort((a,b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = next[1].at; timers.delete(next[0]); next[1].fn(); await flush();
    }
    now = end; await flush();
}
async function hidden(value) { document.hidden = value; [...listeners].forEach(fn => fn()); await flush(); }
async function main() {
    for (const n of [undefined, '', 'bad', 0, -1, 61, .5, 1.5]) assert.equal(R.seconds(n), 2);
    for (const n of [2, 2.5, 10, 60]) assert.equal(R.seconds(n), n);
    const sample = { available:true, device:'cell0', ifindex:3, boot_id:'a', ts:10.5, rx:100, tx:200 };
    const next = { ...sample, ts:11.5, rx:1100, tx:700 };
    assert.deepEqual(R.rateDelta(sample, next), { dl:1000, ul:500 });
    for (const bad of [null, {...next, available:false}, {...next, ts:10.5}, {...next, ts:9},
        {...next, rx:99}, {...next, tx:0}, {...next, ifindex:4}, {...next, device:'cell1'}, {...next, boot_id:'b'}])
        assert.equal(R.rateDelta(sample, bad), null);

    let statusCalls = 0, speedCalls = 0, paints = 0, resets = 0, done;
    const stop = R.poll(() => { statusCalls++; return new Promise(resolve => { done = resolve; }); },
        () => paints++, () => 2000, null, () => resets++);
    const stopSpeed = R.poll(() => ++speedCalls, () => {}, () => 1000);
    await advance(0); assert.equal(statusCalls, 1);
    await advance(3100); assert.equal(statusCalls, 1); assert.equal(speedCalls, 4);
    done({}); await flush(); assert.equal(paints, 1);
    await advance(50); assert.equal(statusCalls, 2); // no completion + interval drift
    await hidden(true); await advance(5000); assert.equal(speedCalls, 4);
    await hidden(false); assert.equal(statusCalls, 2); // same lane still in flight
    done({}); await flush(); assert.equal(paints, 1); // response from hidden generation ignored
    await advance(50); assert.equal(statusCalls, 3);
    stop(); stopSpeed(); done({}); await flush(); await advance(10000);
    assert.equal(paints, 1); assert.equal(statusCalls, 3);
    assert.equal(listeners.size, 0); assert.equal(timers.size, 0); assert.equal(resets, 2);

    let errors = 0, calls = 0;
    const stopErrors = R.poll(() => { calls++; throw Error('offline'); }, () => {}, () => 1000, () => errors++);
    await advance(2000); assert.equal(errors, 3); assert.equal(calls, 3);
    stopErrors(); assert.equal(timers.size, 0);
    let attached = true, removedPaints = 0, removedDone;
    R.poll(() => new Promise(r => { removedDone = r; }), () => removedPaints++, () => 1000,
        null, null, () => attached);
    await advance(0); attached = false; removedDone({}); await flush();
    assert.equal(removedPaints, 0); assert.equal(timers.size, 0); assert.equal(listeners.size, 0);

    // A slow live signal must not hold the cache-only metadata lane hostage.
    let liveDone, metaDone, liveCalls = 0, metaCalls = 0;
    const painted = [], progress = {};
    const M = {
        callSignal: () => { liveCalls++; return new Promise(r => { liveDone = r; }); },
        callCells: () => { metaCalls++; return new Promise(r => { metaDone = r; }); },
        mergeCell: (old, next) => Object.assign({}, old, next), translate: x => x
    };
    const locks = new Function('view', 'M', 'R', 'L', 'document', fs.readFileSync(process.argv[3], 'utf8'))(
        { extend: obj => obj }, M, R, {}, document);
    locks._timers = [];
    locks.Q = id => progress[id] || (progress[id] = {classList:{toggle:()=>{}},textContent:''});
    locks.paintServing = data => painted.push(data);
    const livePromise = locks.loadServing(), metaPromise = locks.loadServingMeta();
    assert.equal(locks.loadServing(), livePromise); assert.equal(liveCalls, 1);
    assert.equal(locks.loadServingMeta(), metaPromise); assert.equal(metaCalls, 1);
    metaDone({ cell: {ts:5,partial:1,neigh_pending:1,operator:{name:'Carrier'}}, sig:{ts:5,cfun:1} });
    await flush(); assert.equal(painted.length, 1); assert.equal(painted[0].cfun, 1);
    assert.equal(progress['neighbor-progress'].textContent, '正在更新…');
    locks.unload(); liveDone({ts:6,cfun:1}); await flush();
    assert.equal(painted.length, 1); // no late paint after navigation
    console.log('refresh: cadence, independence, failures, pause/dispose, counters OK');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
