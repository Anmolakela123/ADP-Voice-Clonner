#!/usr/bin/env bash
set -e
command -v docker >/dev/null || { echo 'Docker is required'; exit 1; }
docker info >/dev/null || { echo 'Docker daemon is not running'; exit 1; }
command -v nvidia-smi >/dev/null || { echo 'NVIDIA driver/nvidia-smi is required'; exit 1; }
nvidia-smi
echo 'GPU check passed.'
