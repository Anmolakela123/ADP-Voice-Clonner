from __future__ import annotations

import asyncio
import threading
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import torch
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chatterbox.mtl_tts import ChatterboxMultilingualTTS

BASE = Path(__file__).resolve().parent
PUBLIC = BASE / "public"
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
JOBS = DATA / "jobs"
for p in (UPLOADS, OUTPUTS, JOBS):
    p.mkdir(parents=True, exist_ok=True)

MAX_WORDS = int(os.getenv("MAX_WORDS", "10000"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "700"))
DEVICE_ENV = os.getenv("DEVICE", "auto").lower()
MODEL_VERSION = os.getenv("MODEL_VERSION", "v3")

LANGUAGES = ChatterboxMultilingualTTS.get_supported_languages()

app = FastAPI(title="Voice Cloning Studio API", version="1.0.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = None
MODEL_LOCK = threading.Lock()
GENERATION_LOCK = threading.Lock()
JOB_LOCK = asyncio.Lock()
JOBS_MEM: dict[str, dict] = {}


class GenerateRequest(BaseModel):
    language: str = Field(min_length=2, max_length=5)
    text: str = Field(min_length=1, max_length=120000)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    stability: float = Field(default=0.70, ge=0.0, le=1.0)
    expressiveness: float = Field(default=0.50, ge=0.0, le=1.0)
    temperature: float = Field(default=0.80, ge=0.1, le=1.5)
    consent: bool = False


def device_name() -> str:
    if DEVICE_ENV in {"cuda", "cpu", "mps"}:
        return DEVICE_ENV
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text, flags=re.UNICODE))


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def smart_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    # Keep sentence boundaries where possible. Falls back to word boundaries.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences: list[str] = []
    for p in paragraphs:
        pieces = re.split(r"(?<=[.!?।！？])\s+", p)
        sentences.extend([x.strip() for x in pieces if x.strip()])

    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if len(sentence) <= max_chars:
            candidate = f"{buf} {sentence}".strip()
            if len(candidate) <= max_chars:
                buf = candidate
            else:
                if buf:
                    chunks.append(buf)
                buf = sentence
        else:
            words = sentence.split()
            for word in words:
                candidate = f"{buf} {word}".strip()
                if len(candidate) <= max_chars:
                    buf = candidate
                else:
                    if buf:
                        chunks.append(buf)
                    buf = word
    if buf:
        chunks.append(buf)
    return chunks


def save_wav(path: Path, wav, sr: int):
    arr = wav.detach().float().cpu().numpy() if torch.is_tensor(wav) else np.asarray(wav)
    arr = np.squeeze(arr)
    if arr.ndim != 1:
        arr = arr.reshape(-1)
    sf.write(str(path), arr.astype(np.float32), sr, subtype="PCM_16")


def ffmpeg_run(args: list[str]):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-3000:])
    return proc


def normalize_reference(src: Path, dst: Path):
    # Convert to mono 24 kHz, trim long silence, and cap the reference to 20 seconds.
    # Chatterbox's conditioning path consumes a short reference; keeping it clean
    # avoids carrying long room tone through the cloning prompt.
    ffmpeg_run([
        "ffmpeg", "-y", "-i", str(src),
        "-vn", "-ac", "1", "-ar", "24000",
        "-af", "silenceremove=start_periods=1:start_duration=0.15:start_threshold=-42dB:stop_periods=1:stop_duration=0.25:stop_threshold=-42dB",
        "-t", "20",
        str(dst)
    ])


def postprocess_speed(src: Path, dst: Path, speed: float):
    # FFmpeg atempo supports 0.5-2.0 directly.
    ffmpeg_run([
        "ffmpeg", "-y", "-i", str(src),
        "-filter:a", f"atempo={speed:.4f}",
        "-ar", "24000", "-ac", "1",
        str(dst)
    ])


def concat_wavs(paths: list[Path], out: Path, gap_ms: int = 80):
    if not paths:
        raise RuntimeError("No generated chunks.")
    # Use ffmpeg concat demuxer and a short silence between chunks.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        concat_file = td_path / "concat.txt"
        lines = []
        for p in paths:
            escaped = p.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        concat_file.write_text("\n".join(lines), encoding="utf-8")
        ffmpeg_run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-ac", "1", "-ar", "24000",
            "-c:a", "pcm_s16le",
            str(out)
        ])


def wav_to_mp3(src: Path, dst: Path):
    ffmpeg_run([
        "ffmpeg", "-y", "-i", str(src),
        "-codec:a", "libmp3lame", "-b:a", os.getenv("OUTPUT_BITRATE", "192k"),
        str(dst)
    ])


def load_model():
    global MODEL
    if MODEL is None:
        with MODEL_LOCK:
            if MODEL is None:
                dev = device_name()
                MODEL = ChatterboxMultilingualTTS.from_pretrained(
                    device=dev, t3_model=MODEL_VERSION
                )
    return MODEL


def update_job(job_id: str, **kwargs):
    JOBS_MEM.setdefault(job_id, {}).update(kwargs)
    (JOBS / f"{job_id}.json").write_text(
        json.dumps(JOBS_MEM[job_id], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def run_generation(job_id: str, reference_path: Path, req: GenerateRequest):
    # A single GPU should process one generation at a time to avoid VRAM contention.
    GENERATION_LOCK.acquire()
    work = Path(tempfile.mkdtemp(prefix=f"{job_id}-", dir=str(JOBS)))
    try:
        update_job(job_id, status="preparing", progress=3, message="Preparing reference audio")
        ref = work / "reference.wav"
        normalize_reference(reference_path, ref)

        text = clean_text(req.text)
        chunks = smart_chunks(text)
        total = len(chunks)
        if total == 0:
            raise RuntimeError("No usable text after normalization.")

        model = load_model()

        generated: list[Path] = []
        # Stability maps to cfg_weight: higher values keep the reference conditioning
        # stronger; expressiveness maps to Chatterbox's exaggeration control.
        cfg_weight = max(0.0, min(1.0, req.stability))
        exaggeration = max(0.0, min(1.0, req.expressiveness))

        for i, chunk in enumerate(chunks, start=1):
            chunk_path = work / f"chunk_{i:04d}.wav"
            update_job(
                job_id,
                status="generating",
                progress=5 + int((i - 1) / total * 80),
                message=f"Generating section {i} of {total}"
            )

            wav = model.generate(
                chunk,
                language_id=req.language,
                audio_prompt_path=str(ref),
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=req.temperature,
                repetition_penalty=1.2,
                min_p=0.05,
                top_p=1.0,
            )
            save_wav(chunk_path, wav, model.sr)
            generated.append(chunk_path)

        joined = work / "master.wav"
        concat_wavs(generated, joined)

        final_wav = OUTPUTS / f"{job_id}.wav"
        final_mp3 = OUTPUTS / f"{job_id}.mp3"
        if abs(req.speed - 1.0) > 0.001:
            postprocess_speed(joined, final_wav, req.speed)
        else:
            shutil.copy2(joined, final_wav)
        wav_to_mp3(final_wav, final_mp3)

        update_job(
            job_id,
            status="completed",
            progress=100,
            message="Voice generation complete",
            wav_url=f"/api/files/{job_id}.wav",
            mp3_url=f"/api/files/{job_id}.mp3",
            chunks=total,
            words=count_words(text),
        )
    except Exception as exc:
        update_job(job_id, status="error", progress=0, message=str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:
            reference_path.unlink(missing_ok=True)
        except Exception:
            pass
        GENERATION_LOCK.release()


@app.get("/health")
async def health():
    return {
        "ok": True,
        "model_loaded": MODEL is not None,
        "device": device_name(),
        "languages": len(LANGUAGES),
    }


@app.get("/api/status")
async def api_status():
    return {
        "ok": True,
        "backend": "online",
        "model_loaded": MODEL is not None,
        "device": device_name(),
        "languages": len(LANGUAGES),
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((PUBLIC / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=PUBLIC), name="static")


@app.get("/api/languages")
async def languages():
    return [{"code": k, "name": v} for k, v in LANGUAGES.items()]


@app.post("/api/analyze-reference")
async def analyze_reference(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
        raise HTTPException(400, "Unsupported audio format.")
    tmp = UPLOADS / f"analysis-{uuid.uuid4().hex}{suffix}"
    size = 0
    with tmp.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "Audio file is too large.")
            f.write(chunk)

    normalized = tmp.with_suffix(".wav")
    try:
        normalize_reference(tmp, normalized)
        data, sr = sf.read(normalized)
        duration = len(data) / sr if sr else 0
        rms = float(np.sqrt(np.mean(np.square(data)))) if len(data) else 0
        clipping = float(np.mean(np.abs(data) >= 0.999)) if len(data) else 0
        quality = "excellent" if duration >= 8 and rms > 0.01 and clipping < 0.01 else "good"
        return {
            "ok": True,
            "filename": file.filename,
            "duration": round(duration, 2),
            "sample_rate": sr,
            "rms": round(rms, 4),
            "clipping": round(clipping, 4),
            "quality": quality,
        }
    except Exception as exc:
        raise HTTPException(400, f"Could not analyze audio: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)
        normalized.unlink(missing_ok=True)


@app.post("/api/generate")
async def generate(
    background: BackgroundTasks,
    reference: UploadFile = File(...),
    language: str = Form(...),
    text: str = Form(...),
    speed: float = Form(1.0),
    stability: float = Form(0.70),
    expressiveness: float = Form(0.50),
    temperature: float = Form(0.80),
    consent: str = Form("false"),
):
    language = language.strip().lower()
    if language not in LANGUAGES:
        raise HTTPException(400, "Unsupported language.")
    if consent.lower() != "true":
        raise HTTPException(400, "Voice-cloning consent confirmation is required.")

    words = count_words(text)
    if words < 1:
        raise HTTPException(400, "Please enter text.")
    if words > MAX_WORDS:
        raise HTTPException(400, f"Maximum {MAX_WORDS:,} words per generation.")

    try:
        speed = float(speed)
        stability = float(stability)
        expressiveness = float(expressiveness)
        temperature = float(temperature)
    except ValueError as exc:
        raise HTTPException(400, "Invalid voice settings.") from exc

    suffix = Path(reference.filename or "").suffix.lower()
    if suffix not in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
        raise HTTPException(400, "Unsupported reference audio format.")

    job_id = uuid.uuid4().hex
    stored = UPLOADS / f"{job_id}{suffix}"
    size = 0
    with stored.open("wb") as f:
        while chunk := await reference.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                stored.unlink(missing_ok=True)
                raise HTTPException(413, "Reference audio is too large.")
            f.write(chunk)

    req = GenerateRequest(
        language=language,
        text=text,
        speed=speed,
        stability=stability,
        expressiveness=expressiveness,
        temperature=temperature,
        consent=True,
    )
    update_job(
        job_id,
        status="queued",
        progress=0,
        message="Queued for generation",
        created_at=time.time(),
        words=words,
    )
    background.add_task(run_generation, job_id, stored, req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = JOBS_MEM.get(job_id)
    if not job:
        path = JOBS / f"{job_id}.json"
        if path.exists():
            job = json.loads(path.read_text(encoding="utf-8"))
    if not job:
        raise HTTPException(404, "Job not found.")
    return job


@app.get("/api/files/{filename}")
async def get_file(filename: str):
    safe = Path(filename).name
    path = OUTPUTS / safe
    if not path.exists():
        raise HTTPException(404, "File not found.")
    media = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    return FileResponse(path, media_type=media, filename=safe)


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    JOBS_MEM.pop(job_id, None)
    for p in [JOBS / f"{job_id}.json", OUTPUTS / f"{job_id}.wav", OUTPUTS / f"{job_id}.mp3"]:
        p.unlink(missing_ok=True)
    return {"ok": True}
