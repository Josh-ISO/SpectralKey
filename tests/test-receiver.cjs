// Deterministic client tests: node tests/test-receiver.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../frontend/js');
const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
assert(html.includes('id="waterfall"'), 'The renderer requires its canvas');
for (const id of fs.readFileSync(path.join(root, 'receiver.js'), 'utf8').matchAll(/byId\('([^']+)'\)/g)) {
    assert(html.includes(`id="${id[1]}"`), `Missing receiver element: ${id[1]}`);
}
const elements = new Map(), timers = new Map(), sockets = [], buffers = [];
let clock = 1000, timerId = 0;
function element(id) {
    if (!elements.has(id)) elements.set(id, {value: '', disabled: false, textContent: '',
        reportValidity: () => true, addEventListener(name, handler) { this[name] = handler; }});
    return elements.get(id);
}
element('receiver-frequency').value = '7100'; element('receiver-zoom').value = '5'; element('receiver-mode').value = 'usb';
class Socket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 1; this.sent = []; sockets.push(this); }
    send(data) { this.sent.push(JSON.parse(data)); }
    close() { this.readyState = 3; }
}
class Plot {
    constructor() { this.wf = {width: 1024, height: 1024}; this.ctx_wf = {clearRect() {}}; }
    setRange() {} setCenterHz() {} setSpanHz() {} resize() {} toggleColor() {} addData(data) { this.data = data; }
}
class AudioContextMock {
    constructor() { this.state = 'running'; this.currentTime = 0; }
    createGain() { return {gain: {value: 0}, connect() {}}; }
    async resume() {}
    createBuffer(channels, length, rate) {
        const data = new Float32Array(length); buffers.push(data);
        return {duration: length / rate, getChannelData: () => data};
    }
    createBufferSource() { return {connect() {}, disconnect() {}, stop() {}, start() {}}; }
}
const context = vm.createContext({console, ArrayBuffer, Uint8Array, Float32Array, DataView,
    Date: {now: () => clock}, Math: Object.assign(Object.create(Math), {random: () => 0}),
    WebSocket: Socket, Spectrum: Plot, AudioContext: AudioContextMock,
    setTimeout: (fn, delay) => { timers.set(++timerId, {fn, delay}); return timerId; },
    clearTimeout: id => timers.delete(id), setInterval: () => ++timerId, clearInterval() {},
    document: {getElementById: element, addEventListener() {}},
    location: {protocol: 'https:', host: 'localhost:8765'},
    window: {addEventListener() {}}, ResizeObserver: class { observe() {} }
});
vm.runInContext(fs.readFileSync(path.join(root, 'audio.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'receiver.js'), 'utf8'), context);
const run = expression => vm.runInContext(expression, context);
async function main() {
    element('receiver-controls').submit({preventDefault() {}});
    assert.equal(sockets[0].url, 'wss://localhost:8765/ws/receiver');
    sockets[0].onopen();
    assert.equal(sockets[0].sent[0].frequency, 7100);
    for (const delay of [1000, 2000, 4000, 8000, 16000, 30000, 30000]) {
        const socket = sockets.at(-1);
        socket.onerror(); socket.onclose();
        assert.equal(timers.size, 1, 'Must schedule only one retry');
        const [id, timer] = [...timers][0];
        assert.equal(timer.delay, delay);
        timers.delete(id); timer.fn();
    }
    sockets.at(-1).onerror();
    element('disconnect-receiver').onclick();
    assert.equal(timers.size, 0);
    assert.equal(run('wanted'), false);
    element('receiver-controls').submit({preventDefault() {}});
    const ws = sockets.at(-1);
    ws.onmessage({data: JSON.stringify({type: 'error', message: 'Session limit reached', retry: false})});
    assert.equal(timers.size, 0);
    assert.equal(run('wanted'), false);
    await run('audio.enable()');
    const frame = new ArrayBuffer(18);
    const bytes = new Uint8Array(frame); bytes.set([83, 78, 68]);
    const view = new DataView(frame);
    [-32768, 0, 16384, 32767].forEach((value, index) => view.setInt16(10 + index * 2, value));
    context.frame = frame;
    run('audio.push(frame)');
    assert.deepEqual(Array.from(buffers.at(-1)), [-1, 0, 0.5, 32767 / 32768]);
    run('audio.context.currentTime = 10; audio.push(frame)');
    assert.equal(run('audio.sources.size'), 1, 'Stale audio must be discarded');
    run('audio.mute()');
    assert.equal(run('audio.sources.size'), 0);
    assert.equal(run('audio.gain.gain.value'), 0);
    element('receiver-controls').submit({preventDefault() {}});
    const active = sockets.at(-1);
    const wf = new ArrayBuffer(1040); new Uint8Array(wf).set([87, 47, 70]);
    new Uint8Array(wf).fill(155, 16);
    active.onmessage({data: wf}); clock += 11000; active.onmessage({data: wf});
    assert.equal(run('attempt'), 0);
    assert.equal(run('spectrum.data[0]'), -100);
    run('disconnect()');
    console.log('PASS: WSS-only URL, tuning, exponential backoff cap, duplicate-event handling, retry cancellation, PCM decoding, mute, stale-buffer cleanup, healthy reset.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
