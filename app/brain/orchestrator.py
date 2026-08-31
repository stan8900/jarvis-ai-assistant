from __future__ import annotations

from functools import lru_cache

from app.brain.prompts import build_system_prompt
from app.brain.tool_router import ToolRouter
from app.core.config import get_settings
from app.llm.base import LLMClient
from app.memory.long_term_memory import LongTermMemory
from app.memory.redis_memory import RedisMemory
from app.voice.tts_base import TextToSpeech


class ConversationOrchestrator:
    def __init__(
        self,
        llm: LLMClient,
        memory: RedisMemory,
        long_term_memory: LongTermMemory | None = None,
        tool_router: ToolRouter | None = None,
        tts: TextToSpeech | None = None,
    ) -> None:
        self.llm = llm
        self.memory = memory
        self.long_term_memory = long_term_memory
        self.tool_router = tool_router or ToolRouter()
        self.tts = tts

    async def respond_to_text(
        self,
        message: str,
        session_id: str = "default",
        user_id: str = "sultan",
    ) -> dict[str, str]:
        clean_message = message.strip()
        tool_result = await self.tool_router.route(clean_message)
        if tool_result is not None:
            response = tool_result.content
            self.memory.add_message(session_id, "user", clean_message)
            self.memory.add_message(session_id, "assistant", response)
            audio = None
            if self.tts is not None:
                audio = self.tts.synthesize(response)
            self._remember_long_term(
                session_id=session_id,
                user_id=user_id,
                user_message=clean_message,
                assistant_response=response,
                tool_name=tool_result.name,
            )
            return {
                "response": response,
                "session_id": session_id,
                "user_id": user_id,
                "model": f"tool:{tool_result.name}",
                "audio": audio,
            }

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
        self._remember_long_term(
            session_id=session_id,
            user_id=user_id,
            user_message=clean_message,
            assistant_response=response,
            tool_name=None,
        )
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

    def _remember_long_term(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        assistant_response: str,
        tool_name: str | None,
    ) -> None:
        if self.long_term_memory is None:
            return
        self.long_term_memory.add_interaction(
            session_id=session_id,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            tool_name=tool_name,
        )


@lru_cache(maxsize=1)
def get_orchestrator() -> ConversationOrchestrator:
    from app.llm.ollama_client import OllamaClient

    settings = get_settings()
    return ConversationOrchestrator(
        llm=OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.request_timeout_seconds,
        ),
        memory=RedisMemory(redis_url=settings.redis_url),
        long_term_memory=LongTermMemory(postgres_url=settings.postgres_url),
        tool_router=ToolRouter(),
    )
