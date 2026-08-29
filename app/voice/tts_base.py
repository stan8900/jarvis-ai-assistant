from abc import ABC, abstractmethod


DEFAULT_TTS_PROVIDER = "xtts"
SUPPORTED_TTS_PROVIDERS = {"piper", "xtts"}


class TextToSpeech(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice_id: str = "default") -> bytes | None:
        """Return WAV bytes for text, or None when synthesis is unavailable."""
