import io
import logging
import os
import wave
from functools import cached_property
from pathlib import Path

from app.voice.tts_base import TextToSpeech


logger = logging.getLogger(__name__)


class PiperVoiceTTS(TextToSpeech):
    def __init__(
        self,
        voice_name: str = "en_GB-alan-medium",
        voices_dir: str = "/Volumes/USB/jarvis-cache/piper-voices",
        use_cuda: bool = False,
    ) -> None:
        self.voice_name = voice_name
        self.voices_dir = Path(voices_dir)
        self.use_cuda = use_cuda

    @cached_property
    def _voice(self):
        try:
            os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
            from piper import PiperVoice
        except Exception as exc:
            logger.error("Piper TTS library is not available: %s", exc)
            return None

        model_path = self.voices_dir / f"{self.voice_name}.onnx"
        config_path = self.voices_dir / f"{self.voice_name}.onnx.json"
        if not model_path.exists() or not config_path.exists():
            logger.error(
                "Piper voice model is missing: %s and %s",
                model_path,
                config_path,
            )
            return None

        try:
            return PiperVoice.load(
                model_path,
                config_path=config_path,
                use_cuda=self.use_cuda,
                download_dir=self.voices_dir,
            )
        except Exception as exc:
            logger.error("Failed to load Piper voice '%s': %s", self.voice_name, exc)
            return None

    def synthesize(self, text: str, voice_id: str = "default") -> bytes | None:
        clean_text = text.strip()
        if not clean_text:
            logger.error("Piper synthesis skipped: empty text.")
            return None

        voice = self._voice
        if voice is None:
            return None

        try:
            output = io.BytesIO()
            with wave.open(output, "wb") as wav_file:
                voice.synthesize_wav(clean_text, wav_file)
            return output.getvalue()
        except Exception as exc:
            logger.error("Piper synthesis failed; falling back to text only: %s", exc)
            return None

    def warm_up(self) -> bool:
        return self._voice is not None


def default_piper_voices_dir() -> str:
    return os.getenv(
        "JARVIS_PIPER_VOICES_DIR",
        os.path.join(os.getenv("XDG_CACHE_HOME", "/Volumes/USB/jarvis-cache"), "piper-voices"),
    )
