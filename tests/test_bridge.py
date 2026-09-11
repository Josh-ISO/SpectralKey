"""HTTPS/WSS bridge integration checks; --live uses the configured public receiver."""
import asyncio
import importlib.util
import json
import ssl
import struct
import sys
from pathlib import Path
from aiohttp import ClientSession, WSMsgType, web

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / 'backend'))
spec = importlib.util.spec_from_file_location('bridge_server', PROJECT / 'backend/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


async def verify(live=False):
    calls = []
    closed = []
    async def fake_receiver(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        kind = request.match_info['kind']
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            calls.append(message.data)
            if message.data.startswith('SET auth'):
                await ws.send_bytes(b'MSG load_cfg=PRIVATE_RECEIVER_ADDRESS')
                if kind == 'SND':
                    await ws.send_bytes(b'MSG audio_rate=12000 sample_rate=12000')
                else:
                    await ws.send_bytes(b'MSG bandwidth=30000000 freq_offset=0 wf_setup')
            if kind == 'SND' and message.data.startswith('SET mod='):
                await ws.send_bytes(b'SND' + struct.pack('<BI', 0, 1) + b'\0\0' + struct.pack('>hhhh', -32768, 0, 16384, 32767))
            if kind == 'W/F' and message.data.startswith('SET zoom='):
                fields = dict(item.split('=') for item in message.data.split()[1:])
                zoom = int(fields['zoom'])
                span = 30000000 / 2**zoom
                start = round((float(fields['cf']) * 1000 - span / 2) * (1024 * 2**14) / 30000000)
                for _ in range(3):
                    await ws.send_bytes(b'W/F ' + struct.pack('<III', start, zoom, 1) + bytes([155]) * 1024)
        closed.append(kind)
        return ws

    fake = web.Application()
    fake.router.add_get('/{session}/{kind:.*}', fake_receiver)
    fake_runner = web.AppRunner(fake)
    await fake_runner.setup()
    fake_site = web.TCPSite(fake_runner, '127.0.0.1', 0)
    await fake_site.start()
    fake_port = fake_site._server.sockets[0].getsockname()[1]
    app = server.create_app(server.UPSTREAM if live else f'http://127.0.0.1:{fake_port}')
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0, ssl_context=server.tls_context())
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f'https://127.0.0.1:{port}'
    client_ssl = ssl.create_default_context(cafile=str(PROJECT / '.tls/localhost.pem'))
    try:
        async with ClientSession() as client:
            for route in server.FILES:
                async with client.get(base + route, ssl=client_ssl) as response:
                    assert response.status == 200, route
                    assert b'proxy.kiwisdr.com' not in await response.read(), route
            async with client.get(base + '/signal_observatory.py', ssl=client_ssl) as response:
                assert response.status == 404
            async with client.get(base + '/ws/receiver', headers={'Origin': 'https://foreign.test'}, ssl=client_ssl) as response:
                assert response.status == 403
            counts = {'sweep': 0, 'SND': 0}
            async with client.ws_connect(base + '/ws/receiver', origin=base, ssl=client_ssl) as ws:
                async with asyncio.timeout(90):
                    while not all(counts.values()):
                        message = await ws.receive()
                        if message.type == WSMsgType.TEXT:
                            data = json.loads(message.data)
                            assert 'PRIVATE' not in message.data
                            assert 'proxy.kiwisdr.com' not in message.data
                            if data['type'] == 'sweep':
                                counts['sweep'] += 1
                                assert len(data['bins']) == 2048
                                assert 0 < data['highHz'] - data['lowHz'] <= 64000000
                                assert abs(data['binWidthHz'] * len(data['bins']) - (data['highHz'] - data['lowHz'])) < .01
                                if not live:
                                    assert data['highHz'] - data['lowHz'] == 30000000
                                    assert all(value == -100 for value in data['bins'])
                            if data['type'] == 'error':
                                raise AssertionError(data)
                        elif message.type == WSMsgType.BINARY:
                            tag = message.data[:3].decode()
                            counts[tag] += 1
                            if tag == 'SND':
                                assert (len(message.data) - 10) % 2 == 0
                                assert not message.data[3] & 0x18
                        else:
                            raise AssertionError(f'Unexpected message {message.type}')
                if not live:
                    await ws.send_json(dict(type='tune', frequency=7100, zoom=5, mode='usb'))
                    async with asyncio.timeout(3):
                        while True:
                            message = await ws.receive()
                            if message.type == WSMsgType.TEXT and json.loads(message.data)['type'] == 'error':
                                assert json.loads(message.data)['retry'] is False
                                break
            for _ in range(20):
                if not app['active']:
                    break
                await asyncio.sleep(.05)
            assert not app['active'], 'Client did not release its receiver session'
            if not live:
                assert 'SET compression=0' in calls
                assert 'SET wf_comp=0' in calls
                assert len(set(call for call in calls if call.startswith('SET zoom='))) == 8
                assert sorted(closed) == ['SND', 'W/F']
            print('PASS: verified TLS, same-origin WSS, sanitized metadata, automatic full-band sweep, audio, rejected manual tuning, cleanup.', counts)
    finally:
        await runner.cleanup()
        await fake_runner.cleanup()


if __name__ == '__main__':
    asyncio.run(verify('--live' in sys.argv))
