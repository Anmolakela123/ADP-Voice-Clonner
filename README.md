# VoiceForge AI Studio — Single Server

This build is designed to run the **website and Chatterbox Multilingual V3 voice engine from the same server and same origin**.

## Important

Do **not** deploy only `index.html` to GitHub Pages if you want voice cloning. GitHub Pages is static hosting and cannot run the Python/Chatterbox inference engine.

Use a Linux server with an NVIDIA GPU and Docker + NVIDIA Container Toolkit. After deployment, open the **server URL** in the browser.

## Deploy

1. Put all ZIP files in one server directory.
2. Make sure `nvidia-smi` works on the host.
3. Run:

```bash
chmod +x deploy.sh healthcheck.sh
./deploy.sh
```

4. Open `http://SERVER-IP/`.
5. The website will show **GPU engine online** when the backend is connected.
6. The first generation downloads the Chatterbox model into the persistent Docker volume; this can take time and disk space.

For a domain, point the domain to the server and put HTTPS in front using your normal reverse proxy/Cloudflare setup. The application itself is already same-origin, so no frontend/backend URL configuration is needed.

## What this fixes

- No separate frontend/backend hosting is required.
- No `/api` calls to a GitHub Pages domain.
- No `frontend/`, `backend/`, `assets/`, `css/`, or `js/` folders are required in the ZIP.
- The browser checks `/health` on startup and shows a clear connection error instead of hanging on “Generating”.
- Reference audio is normalized to a short clean conditioning sample before cloning.
- Generation supports up to 10,000 words per run and exports MP3 + WAV.

## Hardware

A CUDA-capable NVIDIA GPU is strongly recommended. CPU mode is available through `DEVICE=cpu`, but generation can be very slow.

## Consent

Only clone voices you are authorized to clone. The UI requires an explicit permission confirmation.

## Verification

- `GET /health` confirms the server is alive.
- `GET /api/status` reports backend/device state.
- The browser's startup check reports whether the voice engine is connected.

The source package is validated for structure and syntax, but actual GPU inference depends on the target server's NVIDIA driver, CUDA runtime, network access to the model registry, available VRAM, and installed Docker/NVIDIA runtime.
