FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip ffmpeg libsndfile1 git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY main.py /app/main.py
COPY index.html styles.css app.js config.js logo.svg upload.svg /app/public/

RUN mkdir -p /app/data/uploads /app/data/outputs /app/data/jobs /app/public

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=10 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
