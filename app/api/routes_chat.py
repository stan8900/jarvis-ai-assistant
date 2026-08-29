import base64
import os
import tempfile
from functools import lru_cache

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.brain.orchestrator import ConversationOrchestrator, get_orchestrator
from app.core.config import get_settings
from app.llm.ollama_client import OllamaError
from app.api.routes_voice import get_tts
from app.voice.stt_base import STTError, SpeechToText
from app.voice.stt_whisper import FasterWhisperSTT
from app.voice.tts_base import TextToSpeech


router = APIRouter(prefix="/chat", tags=["chat"])


class TextChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(default="default", min_length=1)
    user_id: str = Field(default="sultan", min_length=1)


class TextChatResponse(BaseModel):
    response: str
    session_id: str
    user_id: str
    model: str
    has_audio: bool = False
    audio_base64: str | None = None


class AudioChatResponse(TextChatResponse):
    transcript: str


@lru_cache(maxsize=1)
def get_stt() -> SpeechToText:
    settings = get_settings()
    return FasterWhisperSTT(model_size=settings.whisper_model)


@router.post("/text", response_model=TextChatResponse)
async def chat_text(
    request: TextChatRequest,
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    tts: TextToSpeech = Depends(get_tts),
) -> TextChatResponse:
    try:
        orchestrator.tts = tts
        result = await orchestrator.respond_to_text(
            message=request.message,
            session_id=request.session_id,
            user_id=request.user_id,
        )
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    audio = result.pop("audio", None)
    return TextChatResponse(
        has_audio=audio is not None,
        audio_base64=base64.b64encode(audio).decode("ascii") if audio else None,
        **result,
    )


@router.post("/audio", response_model=AudioChatResponse)
async def chat_audio(
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
    user_id: str = Form(default="sultan"),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    stt: SpeechToText = Depends(get_stt),
    tts: TextToSpeech = Depends(get_tts),
) -> AudioChatResponse:
    suffix = os.path.splitext(audio.filename or "")[1] or ".wav"
    temp_path = ""

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            while chunk := await audio.read(1024 * 1024):
                temp_file.write(chunk)

        transcript = stt.transcribe(temp_path)
        orchestrator.tts = tts
        result = await orchestrator.respond_to_text(
            message=transcript,
            session_id=session_id,
            user_id=user_id,
        )
    except STTError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    audio = result.pop("audio", None)
    return AudioChatResponse(
        transcript=transcript,
        has_audio=audio is not None,
        audio_base64=base64.b64encode(audio).decode("ascii") if audio else None,
        **result,
    )
