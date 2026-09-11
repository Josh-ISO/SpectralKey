// Deterministic client tests: node tests/test-receiver.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../frontend/js');
const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
assert(html.includes('id="oscilloscope"'), 'The renderer requires its canvas');
for (const id of fs.readFileSync(path.join(root, 'receiver.js'), 'utf8').matchAll(/byId\('([^']+)'\)/g)) {
    assert(html.includes(`id="${id[1]}"`), `Missing receiver element: ${id[1]}`);
}
const elements = new Map(), timers = new Map(), sockets = [], buffers = [], animations = new Map();
const listeners = {};
const canvasContext = {canvas: {width: 800, height: 440}, clearRect() {}, fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, createLinearGradient() { return {stops: [], addColorStop(position, color) { this.stops.push([position, color]); }}; }};
let clock = 1000, timerId = 0;
function element(id) {
    if (!elements.has(id)) elements.set(id, {value: '', disabled: false, textContent: '',
        hidden: false, clientWidth: 800, clientHeight: 440, getContext: () => canvasContext, reportValidity: () => true, addEventListener(name, handler) { this[name] = handler; }});
    return elements.get(id);
}
assert(!html.includes('id="receiver-frequency"'));
assert(!html.includes('id="receiver-zoom"'));
assert(!html.includes('id="receiver-mode"'));
assert(!html.includes('id="apply-tuning"'));
class Socket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 1; this.sent = []; sockets.push(this); }
    send(data) { this.sent.push(JSON.parse(data)); }
    close() { this.readyState = 3; }
}
class AudioNodeMock { constructor(context) { this.context = context; } connect() {} }
class AnalyserMock extends AudioNodeMock { constructor(context) { super(context); this.fftSize = 2048; } getByteTimeDomainData(data) { data.fill(128); } }
class AudioContextMock {
    constructor() { this.state = 'running'; this.currentTime = 0; this.sampleRate = 48000; }
    createGain() { return Object.assign(new AudioNodeMock(this), {gain: {value: 1}}); }
    createAnalyser() { return new AnalyserMock(this); }
    async resume() {}
    createBuffer(channels, length, rate) {
        const data = new Float32Array(length); buffers.push(data);
        return {duration: length / rate, getChannelData: () => data};
    }
    createBufferSource() { return {connect() {}, disconnect() {}, stop() {}, start() {}}; }
}
const context = vm.createContext({console, ArrayBuffer, Uint8Array, Float32Array, DataView,
    Date: {now: () => clock}, Math: Object.assign(Object.create(Math), {random: () => 0}),
    WebSocket: Socket, AudioContext: AudioContextMock,
    setTimeout: (fn, delay) => { timers.set(++timerId, {fn, delay}); return timerId; },
    clearTimeout: id => timers.delete(id), setInterval: () => ++timerId, clearInterval() {},
    requestAnimationFrame: fn => { animations.set(++timerId, fn); return timerId; },
    cancelAnimationFrame: id => animations.delete(id),
    document: {hidden: false, getElementById: element, addEventListener(name, fn) { (listeners[name] ||= []).push(fn); }},
    location: {protocol: 'https:', host: 'localhost:8765'},
    window: {addEventListener() {}, AudioNode: AudioNodeMock, AnalyserNode: AnalyserMock}, ResizeObserver: class { observe() {} }
});
vm.runInContext(fs.readFileSync(path.join(root, 'audio.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, '../vendor/oscilloscope/oscilloscope.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'display.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'receiver.js'), 'utf8'), context);
const run = expression => vm.runInContext(expression, context);
async function main() {
    assert.equal(run('audio.context'), null, 'No audio context before a gesture');
    element('receiver-controls').submit({preventDefault() {}});
    assert.equal(sockets[0].url, 'wss://localhost:8765/ws/receiver');
    assert.equal(sockets[0].sent.length, 0, 'Scanning must not send manual tuning commands');
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
    const wf = JSON.stringify({type: 'sweep', completed: 1, lowHz: 0, highHz: 30000000, bins: Array(2048).fill(-100)});
    active.onmessage({data: wf}); clock += 11000; active.onmessage({data: wf});
    assert.equal(run('attempt'), 0);
    assert.equal(element('receiver-frames').textContent, 2);
    const connectionCount = sockets.length;
    await run("display.start()");
    assert.equal(sockets.length, connectionCount, 'Switching views must not reconnect');
    assert.equal(element('scope-screen').hidden, false);
    assert.equal(run('audio.enabled'), false, 'Scope must not enable audible playback');
    assert.equal(animations.size, 1, 'Exactly one scope animation');
    run('audio.push(frame)');
    assert.equal(run('audio.sources.size'), 1, 'Muted scope still receives PCM');
    assert.equal(run('audio.gain.gain.value'), 0);
    run('audio.setVolume(0.9)');
    assert.equal(run('audio.input.gain.value'), 1, 'Scope input is independent of playback volume');
    await run('audio.enable()');
    run('audio.mute()');
    assert.equal(run('audio.sources.size'), 1, 'Mute preserves scope samples');
    active.onmessage({data: JSON.stringify({type: 'sweep-progress', window: 2, windows: 8, frequency: 5625, lowHz: 0, highHz: 30000000})});
    assert.equal(run('audio.sources.size'), 0, 'Advancing a scan clears previous audio');
    assert(element('sweep-progress').textContent.includes('Window 2 of 8'));
    for (const [color, hex] of Object.entries({green: '#a9ffb0', red: '#ff4545', gold: '#ffd166', white: '#ffffff', blue: '#489dff', purple: '#c477ff'})) {
        element('scope-color').change({target: {value: color}});
        run('display.pause(); display.animate()');
        assert.equal(canvasContext.strokeStyle, hex);
        assert.equal(canvasContext.shadowColor, hex);
        assert.equal(sockets.length, connectionCount, 'Color changes must not reconnect');
        assert.equal(animations.size, 1);
    }
    element('scope-color').change({target: {value: 'rainbow'}});
    run('display.pause(); display.animate()');
    const firstGradient = canvasContext.strokeStyle.stops;
    assert.equal(firstGradient.length, 7);
    clock += 100;
    run('display.pause(); display.animate()');
    assert.notDeepEqual(canvasContext.strokeStyle.stops, firstGradient, 'Rainbow colors animate over time');
    context.document.hidden = true;
    listeners.visibilitychange.forEach(fn => fn());
    assert.equal(animations.size, 0, 'Hidden tab stops scope animation');
    assert.equal(run('audio.sources.size'), 0, 'Hidden tab clears audio queue');
    context.document.hidden = false;
    listeners.visibilitychange.forEach(fn => fn());
    assert.equal(animations.size, 1);
    run('display.stop()');
    assert.equal(animations.size, 0);
    assert.equal(run('audio.visualizing'), false);
    await run('Promise.all([display.start(), display.stop()])');
    assert.equal(animations.size, 0, 'A pending start must not resume after stop');
    assert.equal(run('audio.visualizing'), false);
    run('disconnect()');
    console.log('PASS: WSS-only URL, automatic scanning, exponential backoff cap, duplicate-event handling, retry cancellation, PCM decoding, mute, stale-buffer cleanup, healthy reset, trace colors, animated rainbow, muted scope PCM, animation cleanup, rapid start/stop.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
