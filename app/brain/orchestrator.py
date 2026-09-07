from __future__ import annotations

import logging
from time import perf_counter
from functools import lru_cache

from app.brain.prompts import build_system_prompt
from app.brain.tool_router import ToolRouter
from app.core.config import get_settings
from app.llm.base import LLMClient
from app.llm.brain_selector import select_brain
from app.llm.multi_brain import (
    MissingBrainKeyError,
    ask_claude,
    ask_ollama,
    ask_openai,
)
from app.memory.long_term_memory import LongTermMemory
from app.memory.redis_memory import RedisMemory
from app.voice.tts_base import TextToSpeech


logger = logging.getLogger(__name__)


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
        started_at = perf_counter()
        tool_result = await self.tool_router.route(
            clean_message,
            long_term_memory=self.long_term_memory,
        )
        if tool_result is not None:
            response = tool_result.content
            brain_label = f"tool:{tool_result.name}"
            self._log_brain_choice(clean_message, brain_label, started_at)
            self.memory.add_message(session_id, "user", clean_message)
            self.memory.add_message(session_id, "assistant", response)
            audio = None
            if self.tts is not None and tool_result.name != "ide":
                audio = self.tts.synthesize(response)
            self._remember_long_term(
                session_id=session_id,
                user_id=user_id,
                user_message=clean_message,
                assistant_response=response,
                tool_name=brain_label,
            )
            return {
                "response": response,
                "session_id": session_id,
                "user_id": user_id,
                "model": brain_label,
                "audio": audio,
            }

        settings = get_settings()
        recent_context = self.memory.get_context(session_id)
        remembered_facts = (
            self.long_term_memory.facts_context()
            if self.long_term_memory is not None
            else ""
        )
        system_prompt = build_system_prompt(
            user_id=user_id,
            remembered_facts=remembered_facts,
        )
        conversation_messages = [
            *self._to_llm_messages(recent_context),
            {"role": "user", "content": clean_message},
        ]
        selected_brain = select_brain(
            clean_message,
            default_brain=settings.default_brain,
        )
        response, brain_used = await self._ask_brain(
            brain=selected_brain,
            messages=conversation_messages,
            system_prompt=system_prompt,
            settings=settings,
        )
        self._log_brain_choice(clean_message, brain_used, started_at)
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
            tool_name=f"brain:{brain_used}",
        )
        return {
            "response": response,
            "session_id": session_id,
            "user_id": user_id,
            "model": brain_used,
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
        self.long_term_memory.log_interaction(session_id, "user", user_message, tool_name)
        self.long_term_memory.log_interaction(
            session_id,
            "assistant",
            assistant_response,
            tool_name,
        )

    async def _ask_brain(
        self,
        brain: str,
        messages: list[dict[str, str]],
        system_prompt: str,
        settings,
    ) -> tuple[str, str]:
        try:
            if brain == "claude":
                response = await ask_claude(
                    messages=messages,
                    system=system_prompt,
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                )
                return response, "claude"
            if brain == "openai":
                response = await ask_openai(
                    messages=messages,
                    system=system_prompt,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
                return response, "openai"
            response = await ask_ollama(
                messages=messages,
                system=system_prompt,
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                timeout_seconds=settings.request_timeout_seconds,
            )
            return response, "ollama"
        except MissingBrainKeyError as exc:
            logger.warning("%s Trying next available brain.", exc)
            if brain == "claude" and settings.openai_api_key:
                response = await ask_openai(
                    messages=messages,
                    system=system_prompt,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
                return response, "openai"
            if brain == "openai" and settings.anthropic_api_key:
                response = await ask_claude(
                    messages=messages,
                    system=system_prompt,
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                )
                return response, "claude"

            response = await ask_ollama(
                messages=messages,
                system=system_prompt,
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
                timeout_seconds=settings.request_timeout_seconds,
            )
            return response, "ollama"

    @staticmethod
    def _log_brain_choice(user_message: str, brain: str, started_at: float) -> None:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.info('[BRAIN] user="%s" -> %s (%dms)', user_message, brain, elapsed_ms)


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
