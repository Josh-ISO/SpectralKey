/* Bounded Web Audio PCM playback. No sound starts until a user gesture. */
'use strict';
class ReceiverAudio {
    constructor() {
        this.context = null;
        this.rate = 12000;
        this.nextTime = 0;
        this.sources = new Set();
        this.enabled = false;
        this.volume = 0.5;
    }
    async enable() {
        if (!this.context) {
            this.context = new AudioContext();
            this.gain = this.context.createGain();
            this.gain.connect(this.context.destination);
        }
        await this.context.resume();
        this.enabled = true;
        this.gain.gain.value = this.volume;
    }
    mute() { this.enabled = false; this.clear(); if (this.gain) this.gain.gain.value = 0; }
    setVolume(value) {
        this.volume = Math.max(0, Math.min(1, value));
        if (this.gain && this.enabled) this.gain.gain.value = this.volume;
    }
    clear() {
        for (const source of this.sources) { source.onended = null; source.stop(); source.disconnect(); }
        this.sources.clear(); this.nextTime = 0;
    }
    push(buffer) {
        if (!this.enabled || this.context.state !== 'running') return;
        const view = new DataView(buffer);
        if (view.byteLength <= 10 || (view.byteLength - 10) % 2 || view.getUint8(3) & 0x18) return;
        const length = (view.byteLength - 10) / 2;
        const audio = this.context.createBuffer(1, length, this.rate);
        const pcm = audio.getChannelData(0);
        const littleEndian = Boolean(view.getUint8(3) & 0x80);
        for (let i = 0; i < length; i++) pcm[i] = view.getInt16(10 + i * 2, littleEndian) / 32768;
        const now = this.context.currentTime;
        // Drop stale queues after network jitter, throttled tabs, or reconnects.
        if (this.nextTime < now || this.nextTime > now + 0.5) { this.clear(); this.nextTime = now + 0.08; }
        const source = this.context.createBufferSource();
        source.buffer = audio;
        source.connect(this.gain);
        source.onended = () => { this.sources.delete(source); source.disconnect(); };
        this.sources.add(source);
        source.start(this.nextTime);
        this.nextTime += audio.duration;
    }
}
