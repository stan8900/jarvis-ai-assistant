import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("JARVIS_OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("JARVIS_OLLAMA_MODEL", "llama3.2:1b")
    request_timeout_seconds: float = float(os.getenv("JARVIS_REQUEST_TIMEOUT_SECONDS", "60"))
    redis_url: str = os.getenv("JARVIS_REDIS_URL", "redis://localhost:6379/0")
    postgres_url: str = os.getenv(
        "JARVIS_POSTGRES_URL",
        "postgresql://jarvis:jarvis@localhost:5432/jarvis",
    )
    whisper_model: str = os.getenv("JARVIS_WHISPER_MODEL", "base.en")
    xtts_model: str = os.getenv(
        "JARVIS_XTTS_MODEL",
        "tts_models/multilingual/multi-dataset/xtts_v2",
    )
    voices_dir: str = os.getenv("JARVIS_VOICES_DIR", "data/voices")
    voice_id: str = os.getenv("JARVIS_VOICE_ID", "jarvis")
    tts_language: str = os.getenv("JARVIS_TTS_LANGUAGE", "en")
    tts_provider: str = os.getenv("JARVIS_TTS_PROVIDER", "xtts")
    xtts_warm: bool = os.getenv("JARVIS_XTTS_WARM", "true").lower() in {"1", "true", "yes"}
    xtts_python: str | None = os.getenv(
        "JARVIS_XTTS_PYTHON",
        "/Volumes/USB/jarvis-cache/xtts-venv/bin/python",
    )
    piper_voice: str = os.getenv("JARVIS_PIPER_VOICE", "en_GB-alan-medium")
    piper_voices_dir: str = os.getenv(
        "JARVIS_PIPER_VOICES_DIR",
        os.path.join(os.getenv("XDG_CACHE_HOME", "/Volumes/USB/jarvis-cache"), "piper-voices"),
    )
    piper_use_cuda: bool = os.getenv("JARVIS_PIPER_USE_CUDA", "0") == "1"


def get_settings() -> Settings:
    return Settings()
