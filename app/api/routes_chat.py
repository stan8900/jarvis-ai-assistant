import base64
import os
import os
import tempfile
from functools import lru_cache

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request, status

from app.brain.orchestrator import get_orchestrator
from app.core.config import get_settings
from app.llm.multi_brain import BrainError
from app.llm.ollama_client import OllamaError
from app.api.routes_voice import get_tts
from app.voice.stt_base import STTError, SpeechToText
from app.voice.stt_whisper import FasterWhisperSTT
from app.scheduling.parser import detect
from app.scheduling.security import require_owner
from app.scheduling.service import get_service
from app.api.routes_schedule import execute as execute_schedule


router = APIRouter(prefix="/chat", tags=["chat"])


class TextChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=16000)
    session_id: str = Field(default="default", min_length=1, max_length=128)
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
    http_request: Request,
) -> TextChatResponse:
    parsed = detect(request.message)
    if parsed is not None:
        # The native island talks only to the loopback API and does not embed
        # the scheduler secret. Keep the public scheduling routes protected,
        # while allowing this local voice path to use the configured owner.
        local = http_request.client is not None and http_request.client.host in {"127.0.0.1", "::1", "localhost"}
        owner = require_owner(http_request) if http_request.headers.get("authorization") else (os.getenv("JARVIS_SCHEDULER_OWNER", "sultan") if local else require_owner(http_request))
        result = execute_schedule(parsed, owner, request.session_id, http_request, get_service())
        return TextChatResponse(response=result['message'], session_id=request.session_id, user_id=owner, model='tool:scheduling')
    orchestrator = get_orchestrator()
    try:
        # The native macOS island speaks the returned text itself. Avoid
        # blocking chat responses on optional server-side TTS initialization.
        orchestrator.tts = None
        result = await orchestrator.respond_to_text(
            message=request.message,
            session_id=request.session_id,
            user_id=request.user_id,
            schedule_owner=require_owner(http_request) if http_request.headers.get("authorization") else None,
        )
    except OllamaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except BrainError as exc:
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
    http_request: Request,
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
    user_id: str = Form(default="sultan"),
    stt: SpeechToText = Depends(get_stt),
) -> AudioChatResponse:
    suffix = os.path.splitext(audio.filename or "")[1] or ".wav"
    temp_path = ""
    total_bytes = 0

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            while chunk := await audio.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > 25 * 1024 * 1024:
                    raise HTTPException(413, 'Audio uploads are limited to 25 MiB.')
                temp_file.write(chunk)

        transcript = stt.transcribe(temp_path)
        parsed = detect(transcript)
        if parsed is not None:
            owner = require_owner(http_request)
            result = execute_schedule(parsed, owner, session_id, http_request, get_service())
            return AudioChatResponse(response=result['message'], transcript=transcript, session_id=session_id, user_id=owner, model='tool:scheduling')
        orchestrator = get_orchestrator()
        tts = get_tts()
        orchestrator.tts = tts
        result = await orchestrator.respond_to_text(
            message=transcript,
            session_id=session_id,
            user_id=user_id,
            schedule_owner=require_owner(http_request) if http_request.headers.get("authorization") else None,
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
    except BrainError as exc:
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
