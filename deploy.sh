#!/usr/bin/env bash
set -euo pipefail

echo "Checking Docker..."
docker --version >/dev/null

echo "Checking NVIDIA container runtime..."
nvidia-smi >/dev/null

echo "Building and starting VoiceForge..."
docker compose up -d --build

echo "Waiting for the server..."
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:${WEB_PORT:-80}/health >/dev/null; then
    echo "VoiceForge is online: http://127.0.0.1:${WEB_PORT:-80}"
    exit 0
  fi
  sleep 2
done

echo "Server did not become healthy. Run: docker compose logs --tail=200"
exit 1
