from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone


try:
    import psycopg
except ImportError:
    psycopg = None


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactRecord:
    key: str
    value: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class InteractionRecord:
    session_id: str
    role: str
    content: str
    tool_used: str | None
    created_at: datetime


class LongTermMemory:
    def __init__(self, postgres_url: str) -> None:
        self.postgres_url = postgres_url
        self._available = psycopg is not None
        self._fallback_facts: dict[str, FactRecord] = {}
        self._fallback_interactions: list[InteractionRecord] = []
        if self._available:
            self._ensure_schema()

    def remember(self, key: str, value: str) -> None:
        clean_key = _normalize_key(key)
        clean_value = value.strip()
        if not clean_key or not clean_value:
            return

        fact = FactRecord(
            key=clean_key,
            value=clean_value,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        if not self._available:
            self._fallback_facts[clean_key] = fact
            return

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO facts (key, value)
                        VALUES (%s, %s)
                        ON CONFLICT (key)
                        DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                        """,
                        (clean_key, clean_value),
                    )
        except Exception as exc:
            logger.error("Long-term fact write failed: %s", exc)
            self._available = False
            self._fallback_facts[clean_key] = fact

    def recall(self, key: str) -> str | None:
        clean_key = _normalize_key(key)
        if not clean_key:
            return None

        if not self._available:
            fact = self._fallback_facts.get(clean_key)
            return fact.value if fact else None

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT value FROM facts WHERE key = %s", (clean_key,))
                    row = cursor.fetchone()
        except Exception as exc:
            logger.error("Long-term fact read failed: %s", exc)
            self._available = False
            fact = self._fallback_facts.get(clean_key)
            return fact.value if fact else None

        return row[0] if row else None

    def recall_all(self, limit: int = 20) -> list[FactRecord]:
        if not self._available:
            return list(self._fallback_facts.values())[-limit:]

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT key, value, created_at, updated_at
                        FROM facts
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            logger.error("Long-term facts read failed: %s", exc)
            self._available = False
            return list(self._fallback_facts.values())[-limit:]

        return [
            FactRecord(key=row[0], value=row[1], created_at=row[2], updated_at=row[3])
            for row in reversed(rows)
        ]

    def facts_context(self, limit: int = 20) -> str:
        facts = self.recall_all(limit=limit)
        if not facts:
            return ""
        lines = [f"- {fact.key}: {fact.value}" for fact in facts]
        return "Remembered facts about Sultan:\n" + "\n".join(lines)

    def log_interaction(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_used: str | None = None,
    ) -> None:
        clean_content = content.strip()
        if not clean_content:
            return

        record = InteractionRecord(
            session_id=session_id,
            role=role,
            content=clean_content,
            tool_used=tool_used,
            created_at=datetime.now(timezone.utc),
        )

        if not self._available:
            self._add_fallback_interaction(record)
            return

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO interactions (session_id, role, content, tool_used, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            record.session_id,
                            record.role,
                            record.content,
                            record.tool_used,
                            record.created_at,
                        ),
                    )
        except Exception as exc:
            logger.error("Long-term interaction write failed: %s", exc)
            self._available = False
            self._add_fallback_interaction(record)

    def add_interaction(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        assistant_response: str,
        tool_name: str | None = None,
    ) -> None:
        self.log_interaction(session_id, "user", user_message, tool_name)
        self.log_interaction(session_id, "assistant", assistant_response, tool_name)

    def recent_interactions(self, user_id: str = "sultan", limit: int = 20) -> list[InteractionRecord]:
        del user_id
        if not self._available:
            return self._fallback_interactions[-limit:]

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT session_id, role, content, tool_used, created_at
                        FROM interactions
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            logger.error("Long-term interaction read failed: %s", exc)
            self._available = False
            return self._fallback_interactions[-limit:]

        return [
            InteractionRecord(
                session_id=row[0],
                role=row[1],
                content=row[2],
                tool_used=row[3],
                created_at=row[4],
            )
            for row in reversed(rows)
        ]

    def _ensure_schema(self) -> None:
        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS facts (
                            id SERIAL PRIMARY KEY,
                            key TEXT UNIQUE NOT NULL,
                            value TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS interactions (
                            id SERIAL PRIMARY KEY,
                            session_id TEXT,
                            role TEXT,
                            content TEXT,
                            tool_used TEXT,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute("ALTER TABLE interactions ADD COLUMN IF NOT EXISTS role TEXT")
                    cursor.execute("ALTER TABLE interactions ADD COLUMN IF NOT EXISTS content TEXT")
                    cursor.execute("ALTER TABLE interactions ADD COLUMN IF NOT EXISTS tool_used TEXT")
                    cursor.execute("ALTER TABLE facts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")
                    cursor.execute(
                        """
                        DO $$
                        BEGIN
                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'interactions'
                                AND column_name = 'user_id'
                            ) THEN
                                ALTER TABLE interactions ALTER COLUMN user_id DROP NOT NULL;
                            END IF;

                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'interactions'
                                AND column_name = 'user_message'
                            ) THEN
                                ALTER TABLE interactions ALTER COLUMN user_message DROP NOT NULL;
                            END IF;

                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'interactions'
                                AND column_name = 'assistant_response'
                            ) THEN
                                ALTER TABLE interactions ALTER COLUMN assistant_response DROP NOT NULL;
                            END IF;
                        END $$;
                        """
                    )
        except Exception as exc:
            logger.error("Long-term memory unavailable: %s", exc)
            self._available = False

    def _add_fallback_interaction(self, record: InteractionRecord) -> None:
        self._fallback_interactions.append(record)
        del self._fallback_interactions[:-500]


def _normalize_key(key: str) -> str:
    return re.sub(r"\s+", " ", key.strip().lower())
