"""Exit 0 if free, 10 for an existing SpectralKey server, 20 for another service."""
import os
import socket
import ssl
import urllib.request
from pathlib import Path


def check(port=8765):
    try:
        with socket.socket() as probe:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(('127.0.0.1', port))
        return 0
    except OSError as exc:
        if exc.errno not in (10048, 98, 48):
            print(f'Cannot bind port {port}. Check local network permissions.')
            return 20

    cert = os.getenv('SPECTRALKEY_TLS_CERT', str(Path(__file__).resolve().parent.parent / '.tls/localhost.pem'))
    try:
        context = ssl.create_default_context(cafile=cert)
        with urllib.request.urlopen(f'https://localhost:{port}', context=context, timeout=3) as response:
            if b'<title>SpectralKey</title>' in response.read(65536):
                print(f'SpectralKey is already running. Open https://localhost:{port}')
                return 10
    except (OSError, ValueError):
        pass
    print(f'Port {port} is occupied by another service or an older server. Stop that server before launching SpectralKey.')
    return 20


if __name__ == '__main__':
    raise SystemExit(check())
