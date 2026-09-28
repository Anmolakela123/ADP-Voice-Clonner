# Voice Cloning Studio — Truly Flat Deployment Package

This package contains **no project subfolders**. All application files are at the ZIP root.

## What it does
- Chatterbox Multilingual V3 voice cloning
- MP3/WAV reference upload
- Hindi + supported Chatterbox multilingual languages
- Up to 10,000 words per generation
- Speed, stability, expressiveness and temperature controls
- MP3 + WAV output
- Same-server Nginx + FastAPI + GPU inference

## Deploy on one NVIDIA GPU server
1. Install Docker and NVIDIA Container Toolkit.
2. Extract this ZIP into an empty directory.
3. Run: `docker compose up -d --build`
4. Open `http://YOUR_SERVER_IP/`
5. First generation downloads the Chatterbox model into the persistent Docker cache.

For HTTPS, put a domain/reverse proxy in front of port 80.

## Important
The ZIP does not contain multi-GB model weights. They are downloaded at runtime.
A real GPU inference test cannot be performed in this development environment, so live deployment still needs to be tested on the target GPU server.

Only clone voices with the speaker's permission/authorization.
