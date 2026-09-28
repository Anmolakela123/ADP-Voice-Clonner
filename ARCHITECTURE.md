# Architecture
Browser -> Nginx -> FastAPI -> Chatterbox V3 -> WAV/MP3

Everything required for the single-server application is in this flat package. Runtime `data/` and Docker model cache are created outside the ZIP when the stack starts.
