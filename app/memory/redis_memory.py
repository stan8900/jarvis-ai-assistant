import json
from datetime import datetime, timezone
from typing import Any

try:
    import redis
except ImportError:
    redis = None


class RedisMemory:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        context_limit: int = 10,
        max_messages: int = 20,
    ) -> None:
        self.redis_url = redis_url
        self.context_limit = context_limit
        self.max_messages = max_messages
        self._fallback: dict[str, list[dict[str, str]]] = {}
        self._client = self._connect()

    def get_context(self, session_id: str) -> list[dict[str, str]]:
        key = self._key(session_id)
        if self._client is None:
            return self._fallback.get(key, [])[-self.context_limit :]

        try:
            items = self._client.lrange(key, -self.context_limit, -1)
            return [json.loads(item) for item in items]
        except Exception:
            self._client = None
            return self._fallback.get(key, [])[-self.context_limit :]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        key = self._key(session_id)

        if self._client is None:
            self._add_fallback(key, message)
            return

        try:
            self._client.rpush(key, json.dumps(message))
            self._client.ltrim(key, -self.max_messages, -1)
        except Exception:
            self._client = None
            self._add_fallback(key, message)

    def _connect(self) -> Any | None:
        if redis is None:
            return None

        try:
            client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def _add_fallback(self, key: str, message: dict[str, str]) -> None:
        messages = self._fallback.setdefault(key, [])
        messages.append(message)
        del messages[:-self.max_messages]

    @staticmethod
    def _key(session_id: str) -> str:
        return f"jarvis:session:{session_id}:messages"
