from functools import cached_property

from app.voice.stt_base import STTError, SpeechToText


class FasterWhisperSTT(SpeechToText):
    def __init__(
        self,
        model_size: str = "base.en",
        device: str = "auto",
        compute_type: str = "default",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    @cached_property
    def _model(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise STTError(
                "faster-whisper is not installed. Run `pip install faster-whisper`."
            ) from exc

        try:
            return WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as exc:
            raise STTError(
                f"Failed to load faster-whisper model '{self.model_size}': {exc}"
            ) from exc

    def transcribe(self, audio_path: str) -> str:
        try:
            segments, _info = self._model.transcribe(audio_path)
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
        except STTError:
            raise
        except Exception as exc:
            raise STTError(f"Failed to transcribe audio file '{audio_path}': {exc}") from exc

        if not transcript:
            raise STTError("No speech was detected in the uploaded audio.")
        return transcript
