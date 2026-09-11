/* Audio oscilloscope with selectable phosphor colors on a black screen. */
'use strict';
class ReceiverDisplay {
    constructor(audio) {
        this.audio = audio;
        this.active = false;
        this.color = 'green';
        this.colors = {green: '#a9ffb0', red: '#ff4545', gold: '#ffd166', white: '#ffffff', blue: '#489dff', purple: '#c477ff'};
        this.scope = null;
        this.frame = null;
        this.selection = 0;
        this.canvas = document.getElementById('oscilloscope');
        this.ctx = this.canvas.getContext('2d');
        this.note = document.getElementById('display-note');
        document.getElementById('scope-color').addEventListener('change', event => this.setColor(event.target.value));
        new ResizeObserver(() => this.resize()).observe(document.getElementById('receiver-visualization'));
        document.addEventListener('visibilitychange', () => {
            this.pause();
            if (!document.hidden && this.active && this.scope) this.animate();
        });
    }
    setColor(color) {
        this.color = color in this.colors || color === 'rainbow' ? color : 'green';
        this.clear();
    }
    async start() {
        const selection = ++this.selection;
        this.active = true;
        this.note.textContent = 'Starting oscilloscope…';
        try {
            await this.audio.setVisualizing(true);
            if (selection !== this.selection) return;
            if (!this.scope) this.scope = new Oscilloscope(this.audio.input, {fftSize: 2048});
            this.resize();
            this.note.textContent = `Received audio waveform · ${(2048 / this.audio.context.sampleRate * 1000).toFixed(1)} ms across screen · normalized amplitude. Audio follows the automatic scan; mute does not stop the trace.`;
            if (!document.hidden) this.animate();
        } catch {
            if (selection !== this.selection) return;
            this.stop();
            this.note.textContent = 'Oscilloscope could not start. Stop and restart the scan to retry; check browser audio permissions.';
        }
    }
    resize() {
        const scale = window.devicePixelRatio || 1;
        this.canvas.width = Math.max(1, Math.round(this.canvas.clientWidth * scale));
        this.canvas.height = Math.max(1, Math.round(this.canvas.clientHeight * scale));
    }
    animate() {
        if (this.frame !== null || !this.scope || document.hidden) return;
        const draw = () => {
            const ctx = this.ctx;
            const width = this.canvas.width, height = this.canvas.height;
            // Fade the previous trace like phosphor, leaving the CSS graticule visible.
            ctx.globalCompositeOperation = 'destination-out';
            ctx.fillStyle = 'rgba(0, 0, 0, 0.24)';
            ctx.fillRect(0, 0, width, height);
            ctx.globalCompositeOperation = 'source-over';
            let color = this.colors[this.color];
            if (this.color === 'rainbow') {
                const gradient = ctx.createLinearGradient(0, 0, width, 0);
                const hue = (Date.now() / 25) % 360;
                for (let i = 0; i <= 6; i++) gradient.addColorStop(i / 6, `hsl(${(hue + i * 60) % 360}, 100%, 65%)`);
                color = gradient;
            }
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5 * (window.devicePixelRatio || 1);
            ctx.shadowColor = this.colors[this.color] || 'rgba(255, 255, 255, .45)';
            ctx.shadowBlur = 9 * (window.devicePixelRatio || 1);
            if (this.audio.sources.size) this.scope.draw(ctx, 0, height * .08, width, height * .84);
            else {
                ctx.beginPath(); ctx.moveTo(0, height / 2); ctx.lineTo(width, height / 2); ctx.stroke();
            }
            this.frame = requestAnimationFrame(draw);
        };
        draw();
    }
    pause() {
        if (this.frame !== null) cancelAnimationFrame(this.frame);
        this.frame = null;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
    stop() {
        ++this.selection;
        this.active = false;
        this.audio.setVisualizing(false);
        this.pause();
    }
    clear() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
}
