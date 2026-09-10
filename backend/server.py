"""HTTPS site and same-origin WSS bridge for SpectralKey."""
import asyncio
import json
import math
import os
import secrets
import ssl
import time
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import urlsplit
from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

PROJECT = Path(__file__).resolve().parent.parent
ROOT = PROJECT / 'frontend'
# Backend-only configuration. Never forwarded to the browser.
UPSTREAM = os.getenv('SPECTRALKEY_RECEIVER', 'http://sdr.gb0snb.com:8073')
FILES = {
    '/licenses.html': 'licenses.html',
    '/': 'index.html', '/index.html': 'index.html',
    '/css/style.css': 'css/style.css', '/js/receiver.js': 'js/receiver.js', '/js/audio.js': 'js/audio.js',
    '/vendor/waterfall/spectrum.js': 'vendor/waterfall/spectrum.js',
    '/vendor/waterfall/colormap.js': 'vendor/waterfall/colormap.js',
    '/assets/images/spectralkey-logo.png': 'assets/images/spectralkey-logo.png',
    '/assets/fonts/Rem-Blick.ttf': 'assets/fonts/Rem-Blick.ttf',
    '/assets/fonts/Unitblock-JpJma.ttf': 'assets/fonts/Unitblock-JpJma.ttf',
    '/assets/images/spectralkey-logo-icon.ico': 'assets/images/spectralkey-logo-icon.ico',
}
# Serve only generated notice files, never arbitrary backend paths.
for notice in (ROOT / 'licenses').glob('*.txt'):
    FILES['/licenses/' + notice.name] = 'licenses/' + notice.name

MODES = {'am': (-4900, 4900), 'usb': (300, 2700), 'lsb': (-2700, -300), 'cw': (300, 700)}


class ReceiverError(Exception):
    def __init__(self, message, retry=True):
        self.retry = retry
        super().__init__(message)


def validate_tuning(data):
    if not isinstance(data, dict) or data.get('type') != 'tune':
        raise ValueError('Unsupported command')
    frequency = float(data['frequency'])
    zoom = int(data['zoom'])
    mode = data['mode']
    if not math.isfinite(frequency) or not 0 <= frequency <= 32000 or not 0 <= zoom <= 14 or mode not in MODES:
        raise ValueError('Invalid tuning')
    return frequency, zoom, mode


class Bridge:
    def __init__(self, browser, upstream):
        self.browser, self.upstream = browser, upstream
        self.streams = {}
        self.ready = set()
        self.frequency, self.zoom, self.mode = 7100, 5, 'usb'
        self.bandwidth, self.offset = 30000000, 0
        self.last_waterfall = self.last_audio = 0

    async def notify(self, **data):
        await asyncio.wait_for(self.browser.send_json(data), 10)

    async def tune(self):
        frequency = max(0, min(self.bandwidth / 1000, self.frequency - self.offset / 1000))
        if 'SND' in self.ready:
            low, high = MODES[self.mode]
            await self.streams['SND'].send_str(f'SET mod={self.mode} low_cut={low} high_cut={high} freq={frequency:.3f}')
        if 'W/F' in self.ready:
            await self.streams['W/F'].send_str(f'SET zoom={self.zoom} cf={frequency:.3f}')

    async def metadata(self, kind, payload):
        ws = self.streams[kind]
        for item in payload.split():
            key, _, value = item.partition('=')
            if key in ('too_busy', 'exclusive_use'):
                raise ReceiverError('Receiver is busy. Retrying shortly.')
            if key == 'badp' and value != '0':
                raise ReceiverError('Receiver access was declined.', retry=False)
            if key in ('ip_limit', 'inactivity_timeout', 'reason_disabled'):
                raise ReceiverError('Receiver session limit reached. Reconnect later.', retry=False)
            if key == 'down':
                raise ReceiverError('Receiver is temporarily unavailable.')
            if key == 'bandwidth' and 0 < float(value) <= 64000000:
                self.bandwidth = float(value)
                await self.notify(type='receiver', bandwidth=self.bandwidth, offset=self.offset)
            if key == 'freq_offset' and math.isfinite(float(value)):
                self.offset = float(value) * 1000
                await self.notify(type='receiver', bandwidth=self.bandwidth, offset=self.offset)
            if key == 'audio_rate' and kind == 'SND':
                await ws.send_str(f'SET AR OK in={int(value)} out=48000')
            if key == 'sample_rate' and kind == 'SND':
                rate = float(value)
                if not 8000 <= rate <= 96000:
                    raise ReceiverError('Unsupported receiver audio rate.', retry=False)
                await self.notify(type='audio', sampleRate=rate)
                if kind not in self.ready:
                    self.ready.add(kind)
                    for command in ('SET compression=0', 'SET squelch=0 max=0',
                                    'SET genattn=0', 'SET gen=0 mix=-1',
                                    'SET agc=1 hang=0 thresh=-100 slope=6 decay=1000 manGain=50'):
                        await ws.send_str(command)
                    await self.tune()
            if key == 'wf_setup' and kind == 'W/F' and kind not in self.ready:
                self.ready.add(kind)
                for command in ('SET wf_comp=0', 'SET maxdb=-10 mindb=-110', 'SET interp=13'):
                    await ws.send_str(command)
                await self.tune()
                await ws.send_str('SET wf_speed=2')

    async def pump(self, kind):
        async for message in self.streams[kind]:
            if message.type != WSMsgType.BINARY:
                continue
            data = message.data
            if data[:3] == b'MSG':
                await self.metadata(kind, data[4:].decode('utf-8', errors='replace'))
            elif data[:3] == b'W/F' and len(data) == 1040:
                self.last_waterfall = asyncio.get_running_loop().time()
                await asyncio.wait_for(self.browser.send_bytes(data), 10)
            elif data[:3] == b'SND' and len(data) > 10 and not data[3] & 0x18:
                # Plain mono PCM only; ignore compressed startup packets and stereo/IQ.
                self.last_audio = asyncio.get_running_loop().time()
                await asyncio.wait_for(self.browser.send_bytes(data), 10)
        raise ReceiverError('Receiver connection ended.')

    async def commands(self):
        async for message in self.browser:
            if message.type != WSMsgType.TEXT:
                continue
            try:
                self.frequency, self.zoom, self.mode = validate_tuning(json.loads(message.data))
                await self.tune()
            except (ValueError, TypeError, KeyError, OverflowError):
                await self.notify(type='error', message='Invalid tuning settings.', retry=False)
                return

    async def heartbeat(self):
        while True:
            await asyncio.sleep(5)
            for ws in self.streams.values():
                await ws.send_str('SET keepalive')
            now = asyncio.get_running_loop().time()
            if now - min(self.last_waterfall, self.last_audio) > 25:
                raise ReceiverError('Receiver stream stalled.')

    async def run(self):
        url = urlsplit(self.upstream)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ReceiverError('Receiver configuration is invalid.', retry=False)
        scheme = 'wss' if url.scheme == 'https' else 'ws'
        session_id = int(time.time() * 1000) + secrets.randbelow(1000)
        async with AsyncExitStack() as stack:
            session = await stack.enter_async_context(ClientSession(timeout=ClientTimeout(total=None, sock_connect=10, sock_read=15)))
            for kind in ('SND', 'W/F'):
                address = f'{scheme}://{url.netloc}{url.path.rstrip("/")}/{session_id}/{kind}'
                ws = await stack.enter_async_context(session.ws_connect(address, max_msg_size=1024*1024))
                self.streams[kind] = ws
                await ws.send_str('SET auth t=kiwi p=')
                await ws.send_str('SET ident_user=SpectralKey')
            self.last_waterfall = self.last_audio = asyncio.get_running_loop().time()
            tasks = [asyncio.create_task(self.pump(kind)) for kind in self.streams]
            tasks += [asyncio.create_task(self.commands()), asyncio.create_task(self.heartbeat())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


async def bridge(request):
    expected = os.getenv('SPECTRALKEY_ORIGIN', f'https://{request.host}')
    if request.headers.get('Origin') != expected:
        raise web.HTTPForbidden(text='Origin rejected')
    browser = web.WebSocketResponse(heartbeat=20, max_msg_size=2048)
    await browser.prepare(request)
    if request.app['active']:
        await browser.send_json(dict(type='error', message='Another SpectralKey session is connected.', retry=False))
        await browser.close()
        return browser
    request.app['active'].add(browser)
    try:
        await Bridge(browser, request.app['upstream']).run()
    except ReceiverError as exc:
        if not browser.closed:
            await browser.send_json(dict(type='error', message=str(exc), retry=exc.retry))
    except (Exception, asyncio.TimeoutError):
        if not browser.closed:
            await browser.send_json(dict(type='error', message='Receiver connection unavailable.', retry=True))
    finally:
        request.app['active'].discard(browser)
        await browser.close()
    return browser


async def static(request):
    filename = FILES.get(request.path)
    if filename is None:
        raise web.HTTPNotFound()
    return web.FileResponse(ROOT / filename, headers={'Cache-Control': 'no-cache'})


async def shutdown(app):
    for ws in list(app['active']):
        await ws.close(code=1001, message=b'Server shutting down')


def create_app(upstream=UPSTREAM):
    app = web.Application(client_max_size=2048)
    app['upstream'], app['active'] = upstream, set()
    app.router.add_get('/ws/receiver', bridge)
    app.router.add_get('/{path:.*}', static)
    app.on_shutdown.append(shutdown)
    return app


def tls_context():
    cert = os.getenv('SPECTRALKEY_TLS_CERT', str(PROJECT / '.tls/localhost.pem'))
    key = os.getenv('SPECTRALKEY_TLS_KEY', str(PROJECT / '.tls/localhost-key.pem'))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    return context


if __name__ == '__main__':
    import argparse
    import subprocess
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', help='Browser executable to open after HTTPS is listening')
    options = parser.parse_args()

    def announce_ready(message):
        print(message, flush=True)
        if options.browser:
            try:
                subprocess.Popen([options.browser, 'https://localhost:8765'])
            except OSError:
                print('Could not open Chrome. Open https://localhost:8765 manually.', flush=True)

    try:
        context = tls_context()
    except (FileNotFoundError, ssl.SSLError):
        raise SystemExit('HTTPS certificate missing or invalid. Run scripts/setup_tls.py or configure SPECTRALKEY_TLS_CERT and SPECTRALKEY_TLS_KEY.')
    try:
        web.run_app(create_app(), host='127.0.0.1', port=8765, ssl_context=context, access_log=None, print=announce_ready)
    except OSError as exc:
        if exc.errno in (10048, 98, 48):
            raise SystemExit('Port 8765 is already in use. If SpectralKey is running, open https://localhost:8765. Otherwise stop the existing server and try again.') from None
        raise
