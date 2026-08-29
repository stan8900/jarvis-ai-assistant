# Sprint 1 - Core Conversation Loop

Status: COMPLETE
Dates: 28-29 August 2026

## Backlog

Task 1 - FastAPI skeleton: Done
Task 2 - Ollama client: Done
Task 3 - Redis memory: Done
Task 4 - faster-whisper STT: Done
Task 5 - XTTS voice clone: Done
Task 5b - Piper TTS fallback: Done
Task 6 - Voice loop CLI: Done
Task 7 - Dependencies: Done
Task 8 - Basic tests: Done - smoke checks passing
Persistent warm XTTS worker: Done
JARVIS personality prompt: Done
Custom voice reference: Done - `data/voices/jarvis_reference.wav`

## Outcome

Sprint 1 produced a fully local voice conversation loop:

```text
Microphone -> faster-whisper -> FastAPI -> Ollama -> XTTS/Piper -> speaker
```

The active stack is self-hosted:

- Backend: FastAPI
- LLM: Ollama with `llama3.2:1b`
- STT: faster-whisper
- Primary TTS: XTTS using `data/voices/jarvis_reference.wav`
- TTS fallback: Piper `en_GB-alan-medium`
- Short-term memory: Redis with in-memory fallback
- Voice loop: `python -m app.cli.voice_loop`

## Current Run Commands

Terminal 1:

```bash
export OLLAMA_MODELS=/Volumes/USB/jarvis-cache/ollama
ollama serve
```

Terminal 2:

```bash
cd /Users/mukhammadsultanjurabekov/Desktop/Projects/Chattingwebsite/untitled\ folder/jarvis-ai-assistant
source .venv/bin/activate

export COQUI_TOS_AGREED=1
export XDG_CACHE_HOME=/Volumes/USB/jarvis-cache
export TMPDIR=/Volumes/USB/jarvis-cache/tmp
export TORCH_HOME=/Volumes/USB/jarvis-cache/torch
export TTS_HOME=/Volumes/USB/jarvis-cache/tts-home
export JARVIS_TTS_PROVIDER=xtts
export JARVIS_XTTS_WARM=true
export JARVIS_VOICE_ID=jarvis
export JARVIS_XTTS_PYTHON=/Volumes/USB/jarvis-cache/xtts-venv/bin/python
export JARVIS_TTS_DEVICE=cpu
export JARVIS_OLLAMA_BASE_URL=http://127.0.0.1:11434
export JARVIS_OLLAMA_MODEL=llama3.2:1b

python -m uvicorn app.main:app
```

Wait for `Application startup complete`, then start Terminal 3:

```bash
cd /Users/mukhammadsultanjurabekov/Desktop/Projects/Chattingwebsite/untitled\ folder/jarvis-ai-assistant
source .venv/bin/activate
python -m app.cli.voice_loop
```

Current JARVIS voice is XTTS using:

```bash
data/voices/jarvis_reference.wav
```

XTTS runs through a persistent warm worker. Startup pays the model load once;
subsequent `/api/voice/speak` requests should return in roughly 7-9 seconds on
this machine.

Piper remains available as a fast fallback:

```bash
export JARVIS_TTS_PROVIDER=piper
export JARVIS_PIPER_VOICE=en_GB-alan-medium
export JARVIS_PIPER_VOICES_DIR=/Volumes/USB/jarvis-cache/piper-voices
```

Generated smoke-test files are on the USB cache:

```bash
/Volumes/USB/jarvis-cache/xtts-direct.wav
/Volumes/USB/jarvis-cache/xtts-endpoint.wav
```

`llama3.2:1b` is now the Sprint 1 local model. If you need the smaller
fallback again:

```bash
JARVIS_OLLAMA_MODEL=tinyllama python -m uvicorn app.main:app --reload --reload-dir app
```

## Voice References

```bash
data/voices/jarvis_reference.wav
data/voices/sultan_reference.wav
```
