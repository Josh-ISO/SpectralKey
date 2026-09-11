"""Build the static third-party notices page from the installed runtime packages."""
from html import escape
from importlib.metadata import distributions
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parent.parent
FRONTEND = PROJECT / 'frontend'
NOTICES = FRONTEND / 'licenses'
NOTICES.mkdir(exist_ok=True)


def notice(name, source):
    target = NOTICES / name
    target.write_bytes(source.read_bytes())
    return f'<a href="licenses/{escape(name)}">{escape(name)}</a>'


oscilloscope = (FRONTEND / 'vendor/oscilloscope/LICENSE').read_text(encoding='utf-8')
rows = []
for package in sorted(distributions(), key=lambda item: item.metadata['Name'].lower()):
    name = package.metadata['Name']
    if name.lower() in ('pip', 'setuptools', 'wheel'):
        continue
    license_name = package.metadata.get('License-Expression') or package.metadata.get('License', 'See included notices').split('\n')[0]
    links = []
    for file in package.files or []:
        if '.dist-info/licenses/' not in str(file).replace('\\', '/'):
            continue
        source = Path(package.locate_file(file))
        if not source.is_file():
            continue
        suffix = str(file).replace('\\', '/').split('/licenses/', 1)[1]
        filename = re.sub(r'[^A-Za-z0-9_.-]', '-', f'{name}-{suffix}') + '.txt'
        links.append(notice(filename, source))
    rows.append(f'<tr><th scope="row">{escape(name)} <span class="small">{escape(package.version)}</span></th><td>{escape(license_name)}</td><td>{"<br>".join(links) or "No separate notice included in installed package."}</td></tr>')
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
python_note = notice('python-LICENSE.txt', python_license) if python_license.exists() else '<a href="https://docs.python.org/3/license.html">Python license</a>'
page = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Licenses &amp; credits — SpectralKey</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
<header><h1>Licenses &amp; credits</h1><a class="btn" href="/">Back to receiver</a></header>
<main class="licenses-page">
  <p>Third-party software and assets used by SpectralKey. These notices describe the included components; they do not set a license for SpectralKey itself.</p>
  <section class="panel license-card" aria-labelledby="oscilloscope-license">
    <h2 id="oscilloscope-license">Audio oscilloscope</h2>
    <p><a href="https://github.com/mathiasvr/audio-oscilloscope">mathiasvr/audio-oscilloscope</a> 1.3.0 by Mathias Rasmussen provides the audio waveform renderer. The MIT-licensed source is vendored with its ES module export removed for classic browser scripts. SpectralKey adds the grid, glow, and trace colors.</p>
    <details><summary>Full MIT license</summary><pre class="license-text">{escape(oscilloscope)}</pre></details>
  </section>
  <section class="panel license-card" aria-labelledby="backend-licenses">
    <h2 id="backend-licenses">Python backend and dependencies</h2>
    <p>aiohttp provides HTTPS and WebSocket connections; cryptography generates the local development certificate. This list includes their installed dependencies and bundled notices.</p>
    <div class="table-wrap"><table><thead><tr><th>Component</th><th>License</th><th>Included notices</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <p>Python runtime: {python_note}</p>
  </section>
  <section class="panel license-card" aria-labelledby="asset-credits">
    <h2 id="asset-credits">Fonts and artwork</h2>
    <ul>
      <li><strong>Unitblock:</strong> the supplied font identifies its license as <a href="https://creativecommons.org/publicdomain/zero/1.0/">Creative Commons Zero v1.0 Universal</a>.</li>
      <li><strong>Rem-Blick:</strong> the supplied font contains “Copyright (c) Richard Polt 2005. Created by www.fontifier.com.” No separate license grant was supplied with this font.</li>
      <li><strong>SpectralKey logo and icon:</strong> project artwork supplied by the project owner.</li>
    </ul>
  </section>
  <section class="panel license-card" aria-labelledby="protocol-credits">
    <h2 id="protocol-credits">Protocol reference and browser APIs</h2>
    <p><a href="https://github.com/jks-prv/kiwiclient">KiwiSDR kiwiclient</a> was used as a receiver protocol reference. The bridge uses WebSockets and the browser’s built-in Web Audio and Canvas APIs.</p>
  </section>
</main>
<footer class="site-footer"><a href="/">Receiver</a><a href="licenses.html" aria-current="page">Licenses &amp; credits</a></footer>
</body>
</html>
'''
(FRONTEND / 'licenses.html').write_text(page, encoding='utf-8')
print('Built licenses.html and bundled component notices.')
