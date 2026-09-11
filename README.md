# SpectralKey

<img width="1080" height="1080" alt="SpectralKey logo" src="https://github.com/user-attachments/assets/06f5d253-9712-4df7-81c6-bea0249d354d" />
SpectralKey is SDR Exploration project. It is currently in development! 

## Secure launch

The app now serves HTTPS and a same-origin WSS bridge. On this checkout the Python environment and localhost certificate have been generated.

For a fresh checkout (Python 3.10+):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/setup_tls.py
```

On Windows, run `./scripts/trust-local-certificate.ps1` once to trust the generated localhost-only server certificate in your current user's certificate store. This is an explicit trust change, not a browser-warning bypass. The certificate is not a certificate authority, only covers localhost/loopback addresses, and expires after 90 days. Its private key stays in the Git-ignored `.tls` directory. To revoke trust, remove the matching **SpectralKey localhost** certificate from the current user's Trusted Root Certification Authorities store. For renewal, stop the server, remove that trust entry and the `.tls` files, then generate and trust a new certificate.

Double-click **Launch SpectralKey.cmd** to open **https://localhost:8765** automatically. The launcher installs missing Python dependencies into `.venv` before checking the localhost certificate; this requires internet access when dependencies are missing. Stop any previous HTTP server first. Use Ctrl+C in the launcher to stop the app. The launcher checks certificate trust rather than silently changing it.

## Receiver and audio

The audio oscilloscope shows the received mono audio waveform over time. Choose **Green**, **Red**, **Gold**, **White**, **Blue**, **Purple**, or animated **Rainbow RGB** from **Trace color**. The screen stays black with a subtle neutral grid; colors affect only the trace and its glow. The oscilloscope starts with **Start scan** and works while sound is muted. Volume does not change trace amplitude. The MIT-licensed [mathiasvr/audio-oscilloscope](https://github.com/mathiasvr/audio-oscilloscope) renderer is included locally. The display measures normalized audio amplitude, not RF voltage.

Click **Start scan** to continuously sweep the remote KiwiSDR's reported frequency range. The server automatically measures eight adjacent windows at zoom 3, verifies each returned frame's position, discards one settling frame, and averages two measured frames in linear power. Four native bins are combined per output bin, producing 2,048 bins per full-band pass. The sweep counter advances after all eight windows have been measured; scan time depends on the remote receiver and network. The status line shows the current window, audio center frequency, and covered range.

Manual frequency, zoom, mode, and Apply tuning controls have been removed. **Stop scan** cancels retries and releases both receiver streams. **Enable audio**, volume, and mute control local playback. Audio and the oscilloscope follow the center of each automatically selected window in USB mode; this is a narrow audio channel, not the waveform of the entire RF band. Audio queues clear when the scan advances.

The independent implementation is in `backend/sweep.py`. [HackRF's documented sweep behavior](https://hackrf.readthedocs.io/en/latest/hackrf_tools.html#hackrf-sweep) provided conceptual inspiration only; no HackRF code was copied or linked. This is a KiwiSDR scanner, not a HackRF hardware driver or command-line-compatible replacement. Frequency coverage and speed are limited by the configured receiver. Power values are receiver-relative and are not calibrated dBm. A pass measures its windows sequentially, not simultaneously.

The browser connects only to `wss://<SpectralKey host>/ws/receiver`. Python maintains paired audio and spectrum-data connections to the configured receiver. Completed sweep bins, scan progress, mono PCM, and selected numeric metadata reach the browser. Receiver addresses and raw configuration messages are not served. Browser-originated manual tuning commands are rejected.

Reconnect delays grow exponentially from 1 second to a maximum of 30 seconds, with jitter. Completed sweep traffic spanning ten seconds resets the backoff. Busy, interrupted, and stalled sessions retry; receiver access refusals and session limits stop retries. Incomplete sweeps are discarded on reconnect. A scan window that cannot complete within 25 seconds causes a retry. The bridge supports one active browser receiver session at a time.

## Backend configuration

- `SPECTRALKEY_RECEIVER`: backend-only HTTP or HTTPS KiwiSDR endpoint, including its actual WebSocket port. The bridge is not an arbitrary URL proxy; tuning is controlled by the automatic scan engine.
- `SPECTRALKEY_TLS_CERT` / `SPECTRALKEY_TLS_KEY`: PEM certificate and key for HTTPS. Defaults to the generated `.tls/localhost.pem` and `.tls/localhost-key.pem`.
- `SPECTRALKEY_ORIGIN`: exact authorized HTTPS browser origin when different from the request host.

The server binds to loopback. For remote deployment, use an appropriate hostname certificate and a configured reverse proxy with WebSocket upgrades. The browser-to-SpectralKey connection is encrypted. The separate receiver connection uses the transport supported by that receiver; a WS-only receiver is not made end-to-end encrypted by this bridge.

## Verification

```powershell
node tests/test-receiver.cjs
.venv\Scripts\python.exe tests/test_sweep.py
.venv\Scripts\python.exe tests/test_bridge.py
.venv\Scripts\python.exe tests/test_bridge.py --live
```

Local tests cover verified TLS/WSS, same-origin enforcement, static asset access, sanitized receiver metadata, PCM forwarding, full-band scan assembly, settling, stale-frame rejection, linear power averaging, upstream cleanup, exponential backoff and cancellation, sample decoding, and audio queue clearing. The live test requires a free public receiver slot.

## Third-party code

Receiver protocol reference: [kiwiclient](https://github.com/jks-prv/kiwiclient). HTTPS and WebSockets use aiohttp; certificate generation uses cryptography. Observation logging remains disabled.

## File structure

```text
SpectralKey/
  Launch SpectralKey.cmd     Double-click launcher
  backend/server.py         HTTPS server and receiver bridge
  backend/sweep.py          Independent automatic scan and power-bin assembly
  frontend/
    index.html              Page layout
    css/style.css           Styles
    js/                     Receiver client and WebAudio playback
    assets/fonts/           Web fonts
    assets/images/          Logo and icon
    vendor/oscilloscope/     Audio waveform renderer and MIT license
  scripts/                  Launch and certificate setup helpers
  tests/                    Python integration and JavaScript client checks
  database/schema.sql       Existing SQL placeholder
  data/                     Saved database and recordings (Git-ignored)
  design/                   Original design assets
  .tls/                     Local certificates (Git-ignored)
  .venv/                    Python environment (Git-ignored)
```

The existing observation data is preserved in `data/`; the current bridge does not use it. `design/Rem-Blick.ttf` preserves the original font source, while the website uses its copy in `frontend/assets/fonts/`. Restart an existing server after this folder migration.

## Licenses page

The receiver footer links to `frontend/licenses.html`. The page includes the oscilloscope MIT notice, installed backend dependency licenses, and font/artwork credits. Bundled license text lives in `frontend/licenses/`. After changing Python dependencies, rebuild it with `.venv\Scripts\python.exe scripts/build_licenses.py`.

Keep the audio canvas (`id="oscilloscope"`) and its scripts in `frontend/index.html`; the credit text can be edited independently on the licenses page.
