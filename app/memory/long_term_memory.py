from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


try:
    import psycopg
except ImportError:
    psycopg = None


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InteractionRecord:
    session_id: str
    user_id: str
    user_message: str
    assistant_response: str
    tool_name: str | None
    created_at: datetime


class LongTermMemory:
    def __init__(self, postgres_url: str) -> None:
        self.postgres_url = postgres_url
        self._available = psycopg is not None
        self._fallback: list[InteractionRecord] = []
        if self._available:
            self._ensure_schema()

    def add_interaction(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        assistant_response: str,
        tool_name: str | None = None,
    ) -> None:
        record = InteractionRecord(
            session_id=session_id,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            tool_name=tool_name,
            created_at=datetime.now(timezone.utc),
        )

        if not self._available:
            self._add_fallback(record)
            return

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO interactions (
                            session_id,
                            user_id,
                            user_message,
                            assistant_response,
                            tool_name,
                            created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.session_id,
                            record.user_id,
                            record.user_message,
                            record.assistant_response,
                            record.tool_name,
                            record.created_at,
                        ),
                    )
        except Exception as exc:
            logger.error("Long-term memory write failed: %s", exc)
            self._available = False
            self._add_fallback(record)

    def recent_interactions(self, user_id: str, limit: int = 20) -> list[InteractionRecord]:
        if not self._available:
            return [record for record in self._fallback if record.user_id == user_id][-limit:]

        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT session_id, user_id, user_message, assistant_response,
                               tool_name, created_at
                        FROM interactions
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (user_id, limit),
                    )
                    rows = cursor.fetchall()
        except Exception as exc:
            logger.error("Long-term memory read failed: %s", exc)
            self._available = False
            return [record for record in self._fallback if record.user_id == user_id][-limit:]

        return [
            InteractionRecord(
                session_id=row[0],
                user_id=row[1],
                user_message=row[2],
                assistant_response=row[3],
                tool_name=row[4],
                created_at=row[5],
            )
            for row in reversed(rows)
        ]

    def _ensure_schema(self) -> None:
        try:
            with psycopg.connect(self.postgres_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS interactions (
                            id BIGSERIAL PRIMARY KEY,
                            session_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            user_message TEXT NOT NULL,
                            assistant_response TEXT NOT NULL,
                            tool_name TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_interactions_user_created
                        ON interactions (user_id, created_at DESC)
                        """
                    )
        except Exception as exc:
            logger.error("Long-term memory unavailable: %s", exc)
            self._available = False

    def _add_fallback(self, record: InteractionRecord) -> None:
        self._fallback.append(record)
        del self._fallback[:-200]
