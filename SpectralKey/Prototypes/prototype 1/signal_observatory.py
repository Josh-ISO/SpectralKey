"""Serve the SpectralKey page locally. Run: python signal_observatory.py"""
import webbrowser

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
url = 'http://127.0.0.1:8765'
chrome_path = 'C:/Program Files/Google/Chrome/Application/chrome.exe %s'
ROOT = Path(__file__).resolve().parent
FILES = {
    "/": ("signal_observatory.html", "text/html; charset=utf-8"),
    "/signal_observatory.html": ("signal_observatory.html", "text/html; charset=utf-8"),
    "/Style.css": ("Style.css", "text/css; charset=utf-8"),
    "/assets/spectralkey-logo.png": ("assets/spectralkey-logo.png", "image/png"),
    "/assets/Rem-Blick.ttf": ("assets/Rem-Blick.ttf", "font/ttf"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        file = FILES.get(urlsplit(self.path).path)
        if file is None:
            self.send_error(404)
            return

        filename, content_type = file
        try:
            content = (ROOT / filename).read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", 8765), Handler) as server:
        print("SpectralKey running at http://127.0.0.1:8765", flush=True)
        
        try:
            server.serve_forever()
            webbrowser.get(chrome_path).open(url)
        except KeyboardInterrupt:
            print("\nStopped.")
