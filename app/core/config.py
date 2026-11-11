import os
from dataclasses import dataclass


def _load_local_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    try:
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                    continue
                key, value = clean_line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    except OSError:
        return


_load_local_env()


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("JARVIS_OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("JARVIS_OLLAMA_MODEL", "llama3.1:8b")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("JARVIS_OPENAI_MODEL", "gpt-4o-mini")
    default_brain: str = os.getenv("JARVIS_DEFAULT_BRAIN", "ollama")
    request_timeout_seconds: float = float(os.getenv("JARVIS_REQUEST_TIMEOUT_SECONDS", "120"))
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
    bold_api_base_url: str = os.getenv("BOLD_API_BASE_URL", "https://bold-production.up.railway.app")
    bold_api_token: str = os.getenv("BOLD_API_TOKEN", "")
    bold_request_timeout_seconds: float = float(os.getenv("BOLD_REQUEST_TIMEOUT_SECONDS", "15"))


def get_settings() -> Settings:
    return Settings()
