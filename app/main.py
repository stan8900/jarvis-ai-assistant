import logging

from fastapi import FastAPI

from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router
from app.api.routes_voice import router as voice_router


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="JARVIS Local Assistant",
        version="0.1.0",
        description="Self-hosted JARVIS core API.",
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")

    @app.on_event("startup")
    async def warm_tts() -> None:
        try:
            from app.api.routes_voice import get_tts
            from app.core.config import get_settings

            settings = get_settings()
            provider = settings.tts_provider.lower().strip()
            if provider == "xtts" and not settings.xtts_warm:
                return

            tts = get_tts()
            warm_up = getattr(tts, "warm_up", None)
            if callable(warm_up):
                warm_up()
        except Exception as exc:
            logger.error("TTS warm-up failed: %s", exc)

    @app.on_event("shutdown")
    async def close_tts() -> None:
        try:
            from app.api.routes_voice import get_tts

            tts = get_tts()
            close = getattr(tts, "close", None)
            if callable(close):
                close()
        except Exception as exc:
            logger.error("TTS shutdown failed: %s", exc)

    return app


app = create_app()
