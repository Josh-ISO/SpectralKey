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

Double-click **Launch SpectralKey.cmd** and open **https://localhost:8765**. Stop any previous HTTP server first. Use Ctrl+C in the launcher to stop the app. The launcher checks certificate trust rather than silently changing it.

## Receiver and audio

Click **Connect**, then **Enable audio** to start sound with a browser user gesture. Choose AM, USB, LSB, or CW and a frequency in kHz, then click **Apply tuning**. Volume and mute affect browser playback. **Colors** cycles the waterfall palette. Disconnect cancels retries, releases the receiver session, and clears queued audio.

The browser connects only to `wss://<SpectralKey host>/ws/receiver`. Python maintains paired sound and waterfall connections to the configured receiver. Only FFT frames, mono PCM frames, and selected numeric metadata reach the browser; receiver addresses and raw Kiwi configuration messages are not served. This hides the upstream address from the page and browser connections, not from someone with access to the server's source or environment.

Reconnect delays grow exponentially from 1 second to a maximum of 30 seconds, with jitter. Ten seconds of healthy waterfall traffic resets the backoff. Busy, interrupted, and stalled sessions retry; receiver access refusals and session limits stop retries. The bridge supports one active browser session at a time. Web Audio resamples the receiver PCM as needed and discards stale playback queues after interruptions.

## Backend configuration

- `SPECTRALKEY_RECEIVER`: backend-only HTTP or HTTPS KiwiSDR endpoint, including its actual WebSocket port. The bridge is not an arbitrary URL proxy and accepts only tuning commands from the page.
- `SPECTRALKEY_TLS_CERT` / `SPECTRALKEY_TLS_KEY`: PEM certificate and key for HTTPS. Defaults to the generated `.tls/localhost.pem` and `.tls/localhost-key.pem`.
- `SPECTRALKEY_ORIGIN`: exact authorized HTTPS browser origin when different from the request host.

The server binds to loopback. For remote deployment, use an appropriate hostname certificate and a configured reverse proxy with WebSocket upgrades. The browser-to-SpectralKey connection is encrypted. The separate receiver connection uses the transport supported by that receiver; a WS-only receiver is not made end-to-end encrypted by this bridge.

## Verification

```powershell
node tests/test-receiver.cjs
.venv\Scripts\python.exe tests/test_bridge.py
.venv\Scripts\python.exe tests/test_bridge.py --live
```

Local tests cover verified TLS/WSS, same-origin enforcement, static asset access, sanitized receiver metadata, PCM and FFT forwarding, upstream cleanup, exponential backoff and cancellation, sample decoding, and audio queue clearing. The live test requires a free public receiver slot.

## Third-party code

The unmodified renderer and colormaps from [jledet/waterfall](https://github.com/jledet/waterfall) are vendored with their MIT license. Receiver protocol reference: [kiwiclient](https://github.com/jks-prv/kiwiclient). HTTPS and WebSockets use aiohttp; certificate generation uses cryptography. Observation logging remains disabled.

## File structure

```text
SpectralKey/
  Launch SpectralKey.cmd     Double-click launcher
  backend/server.py         HTTPS server and receiver bridge
  frontend/
    index.html              Page layout
    css/style.css           Styles
    js/                     Receiver client and WebAudio playback
    assets/fonts/           Web fonts
    assets/images/          Logo and icon
    vendor/waterfall/        Upstream renderer and MIT license
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

The receiver footer links to `frontend/licenses.html`. The page includes the waterfall MIT notice, installed backend dependency licenses, and font/artwork credits. Bundled license text lives in `frontend/licenses/`. After changing Python dependencies, rebuild it with `.venv\Scripts\python.exe scripts/build_licenses.py`.

Keep the receiver canvas (`id="waterfall"`) and its scripts in `frontend/index.html`; the credit text can be edited independently on the licenses page.
