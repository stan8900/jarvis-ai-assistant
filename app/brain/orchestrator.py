from functools import lru_cache

from app.brain.prompts import build_system_prompt
from app.core.config import get_settings
from app.llm.ollama_client import OllamaClient
from app.memory.redis_memory import RedisMemory
from app.voice.tts_base import TextToSpeech


class ConversationOrchestrator:
    def __init__(
        self,
        llm: OllamaClient,
        memory: RedisMemory,
        tts: TextToSpeech | None = None,
    ) -> None:
        self.llm = llm
        self.memory = memory
        self.tts = tts

    async def respond_to_text(
        self,
        message: str,
        session_id: str = "default",
        user_id: str = "sultan",
    ) -> dict[str, str]:
        clean_message = message.strip()
        recent_context = self.memory.get_context(session_id)
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": build_system_prompt(user_id=user_id)},
                *self._to_llm_messages(recent_context),
                {"role": "user", "content": clean_message},
            ]
        )
        self.memory.add_message(session_id, "user", clean_message)
        self.memory.add_message(session_id, "assistant", response)
        audio = None
        if self.tts is not None:
            audio = self.tts.synthesize(response)
        return {
            "response": response,
            "session_id": session_id,
            "user_id": user_id,
            "model": self.llm.model,
            "audio": audio,
        }

    @staticmethod
    def _to_llm_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]


@lru_cache(maxsize=1)
def get_orchestrator() -> ConversationOrchestrator:
    settings = get_settings()
    return ConversationOrchestrator(
        llm=OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.request_timeout_seconds,
        ),
        memory=RedisMemory(redis_url=settings.redis_url),
    )
