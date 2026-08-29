from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Return an assistant response for a chat message list."""
