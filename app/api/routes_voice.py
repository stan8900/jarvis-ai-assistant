from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.voice.tts_base import SUPPORTED_TTS_PROVIDERS, TextToSpeech
from app.voice.tts_piper import PiperVoiceTTS
from app.voice.tts_xtts import XTTSVoice


router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice_id: str = Field(default="default", min_length=1)


@lru_cache(maxsize=1)
def get_tts() -> TextToSpeech:
    settings = get_settings()
    provider = settings.tts_provider.lower().strip()
    if provider == "piper":
        return PiperVoiceTTS(
            voice_name=settings.piper_voice,
            voices_dir=settings.piper_voices_dir,
            use_cuda=settings.piper_use_cuda,
        )
    if provider != "xtts":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Unsupported TTS provider '{settings.tts_provider}'. "
                f"Expected one of: {', '.join(sorted(SUPPORTED_TTS_PROVIDERS))}."
            ),
        )

    return XTTSVoice(
        model_name=settings.xtts_model,
        voices_dir=settings.voices_dir,
        language=settings.tts_language,
        default_voice_id=settings.voice_id,
        warm_worker=settings.xtts_warm,
        worker_python=settings.xtts_python,
    )


@router.post("/speak", response_class=Response)
async def speak(
    request: SpeakRequest,
    tts: TextToSpeech = Depends(get_tts),
) -> Response:
    audio = tts.synthesize(request.text, request.voice_id)
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS synthesis failed. Check provider, model availability, and voice configuration.",
        )

    return Response(content=audio, media_type="audio/wav")
