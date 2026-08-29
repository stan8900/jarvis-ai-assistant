from abc import ABC, abstractmethod


class STTError(RuntimeError):
    pass


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        """Return a transcript for a local audio file path."""
