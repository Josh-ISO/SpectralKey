/* Same-origin secure receiver bridge with bounded reconnect backoff. */
'use strict';
const byId = id => document.getElementById(id);
const audio = new ReceiverAudio();
const display = new ReceiverDisplay(audio);
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
    display.clear();
}
function disconnect(message = 'Disconnected.') {
    wanted = false;
    cleanup();
    display.stop();
    audio.mute();
    byId('audio-toggle').textContent = 'Enable audio';
    byId('connect-receiver').disabled = false;
    byId('disconnect-receiver').disabled = true;
    byId('sweep-progress').textContent = 'Scan stopped.';
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
function receiveSweep(message) {
    if (!Array.isArray(message.bins) || message.bins.length !== 2048 ||
        !message.bins.every(Number.isFinite) || !Number.isFinite(message.lowHz) ||
        !Number.isFinite(message.highHz) || message.highHz <= message.lowHz) {
        retry('Invalid sweep response.'); return;
    }
    lastFrame = Date.now();
    if (!healthySince) healthySince = lastFrame;
    if (lastFrame - healthySince > 10000) attempt = 0;
    byId('receiver-frames').textContent = ++frames;
    status('Scanning · secure connection');
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

    current.onmessage = event => {
        if (socket !== current) return;
        if (event.data instanceof ArrayBuffer) { audio.push(event.data); return; }
        try {
            const message = JSON.parse(event.data);
            if (message.type === 'receiver') { bandwidth = message.bandwidth; frequencyOffset = message.offset; }
            if (message.type === 'audio') audio.rate = message.sampleRate;
            if (message.type === 'sweep') receiveSweep(message);
            if (message.type === 'sweep-progress') {
                lastFrame = Date.now();
                audio.clear();
                byId('sweep-progress').textContent = `Window ${message.window} of ${message.windows} · ${(message.frequency / 1000).toFixed(3)} MHz · ${(message.lowHz / 1e6).toFixed(2)}–${(message.highHz / 1e6).toFixed(2)} MHz`;
                status('Scanning · secure connection');
            }
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
    display.start();
    wanted = true; attempt = 0; frames = 0;
    byId('receiver-frames').textContent = '0';
    byId('sweep-progress').textContent = 'Preparing scan…';
    byId('connect-receiver').disabled = true;
    byId('disconnect-receiver').disabled = false;
    connect();
});
byId('disconnect-receiver').onclick = () => disconnect();
byId('audio-toggle').onclick = async () => {
    if (audio.enabled) { audio.mute(); byId('audio-toggle').textContent = 'Enable audio'; }
    else {
        try { await audio.enable(); byId('audio-toggle').textContent = 'Mute audio'; }
        catch { status('Audio could not start. Check browser audio permissions.'); }
    }
};
byId('audio-volume').oninput = event => audio.setVolume(Number(event.target.value));
window.addEventListener('pagehide', () => { disconnect(); display.stop(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) audio.clear(); });
