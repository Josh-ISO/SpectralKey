/* Same-origin secure receiver bridge with bounded reconnect backoff. */
'use strict';
const byId = id => document.getElementById(id);
const spectrum = new Spectrum('waterfall', {spectrumPercent: 25, wf_rows: 1024});
spectrum.setRange(-130, -30);
const audio = new ReceiverAudio();
let socket = null, retryTimer = null, watchdog = null, wanted = false, attempt = 0;
let bandwidth = 30000000, frequencyOffset = 0, frames = 0, lastFrame = 0, healthySince = 0;
const status = text => { byId('receiver-status').textContent = text; };

function cleanup() {
    clearTimeout(retryTimer); retryTimer = null;
    clearInterval(watchdog); watchdog = null;
    const old = socket; socket = null;
    if (old) old.close();
    healthySince = 0;
    audio.clear();
}
function disconnect(message = 'Disconnected.') {
    wanted = false;
    cleanup();
    audio.mute();
    byId('audio-toggle').textContent = 'Enable audio';
    byId('connect-receiver').disabled = false;
    byId('disconnect-receiver').disabled = true;
    status(message);
}
function retry(message) {
    if (!wanted || retryTimer !== null) return;
    cleanup();
    // 1, 2, 4, 8 ... seconds, plus jitter, capped at 30 seconds.
    const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5) * (1 + Math.random() * 0.2));
    status(`${message} Reconnecting in ${(delay / 1000).toFixed(1)}s…`);
    retryTimer = setTimeout(() => { retryTimer = null; connect(); }, delay);
}
function tune() {
    if (!byId('receiver-controls').reportValidity()) return;
    if (socket?.readyState === WebSocket.OPEN) {
        audio.clear();
        spectrum.binsAverage = undefined;
        spectrum.ctx_wf.clearRect(0, 0, spectrum.wf.width, spectrum.wf.height);
        socket.send(JSON.stringify({type: 'tune', frequency: Number(byId('receiver-frequency').value),
            zoom: Number(byId('receiver-zoom').value), mode: byId('receiver-mode').value}));
    }
}
function receive(buffer) {
    const bytes = new Uint8Array(buffer);
    const tag = String.fromCharCode(...bytes.slice(0, 3));
    if (tag === 'SND') { audio.push(buffer); return; }
    if (tag !== 'W/F' || bytes.length !== 1040) return;
    const header = new DataView(buffer);
    const zoom = header.getUint32(8, true) & 0xffff;
    if (zoom > 14) return;
    lastFrame = Date.now();
    if (!healthySince) healthySince = lastFrame;
    // A briefly opened socket must not reset the backoff.
    if (lastFrame - healthySince > 10000) attempt = 0;
    const start = header.getUint32(4, true) * bandwidth / (1024 * 2 ** 14);
    const span = bandwidth / 2 ** zoom;
    spectrum.setCenterHz(start + span / 2 + frequencyOffset);
    spectrum.setSpanHz(span);
    spectrum.addData(Float32Array.from(bytes.slice(16), value => value - 255));
    byId('receiver-frames').textContent = ++frames;
    status('Live · secure connection');
}
function connect() {
    if (!wanted) return;
    if (location.protocol !== 'https:') {
        disconnect('Open SpectralKey over HTTPS to connect securely.'); return;
    }
    cleanup();
    bandwidth = 30000000; frequencyOffset = 0;
    lastFrame = Date.now();
    status('Connecting securely…');
    let current;
    try { current = new WebSocket(`wss://${location.host}/ws/receiver`); }
    catch { retry('Connection failed.'); return; }
    socket = current;
    current.binaryType = 'arraybuffer';
    current.onopen = () => { if (socket === current) tune(); };
    current.onmessage = event => {
        if (socket !== current) return;
        if (event.data instanceof ArrayBuffer) { receive(event.data); return; }
        try {
            const message = JSON.parse(event.data);
            if (message.type === 'receiver') { bandwidth = message.bandwidth; frequencyOffset = message.offset; }
            if (message.type === 'audio') audio.rate = message.sampleRate;
            if (message.type === 'error') {
                if (message.retry) retry(message.message);
                else disconnect(message.message);
            }
        } catch { retry('Invalid bridge response.'); }
    };
    current.onerror = () => { if (socket === current) retry('Connection interrupted.'); };
    current.onclose = () => { if (socket === current) retry('Connection closed.'); };
    watchdog = setInterval(() => { if (Date.now() - lastFrame > 30000) retry('Stream stalled.'); }, 1000);
}
byId('receiver-controls').addEventListener('submit', event => {
    event.preventDefault();
    wanted = true; attempt = 0; frames = 0;
    byId('receiver-frames').textContent = '0';
    byId('connect-receiver').disabled = true;
    byId('disconnect-receiver').disabled = false;
    connect();
});
byId('disconnect-receiver').onclick = () => disconnect();
byId('apply-tuning').onclick = tune;
byId('waterfall-color').onclick = () => spectrum.toggleColor();
byId('audio-toggle').onclick = async () => {
    if (audio.enabled) { audio.mute(); byId('audio-toggle').textContent = 'Enable audio'; }
    else {
        try { await audio.enable(); byId('audio-toggle').textContent = 'Mute audio'; }
        catch { status('Audio could not start. Check browser audio permissions.'); }
    }
};
byId('audio-volume').oninput = event => audio.setVolume(Number(event.target.value));
new ResizeObserver(() => spectrum.resize()).observe(byId('waterfall'));
window.addEventListener('pagehide', () => disconnect());
document.addEventListener('visibilitychange', () => { if (document.hidden) audio.clear(); });
