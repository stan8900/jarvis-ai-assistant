from __future__ import annotations

import json
import logging
import os
from zoneinfo import ZoneInfo
from datetime import datetime
from pathlib import Path
from typing import Any

from app.integrations.calendar import get_today_event_summary
from app.integrations.weather import get_weather


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIEF_CONFIG_PATH = PROJECT_ROOT / "data" / "brief_config.json"



async def get_morning_brief(owner_id: str | None = None) -> str:
    now = datetime.now(ZoneInfo(os.getenv("JARVIS_TIMEZONE", "Europe/London")))
    config = load_brief_config()
    tasks = config.get("daily_tasks") or []

    greeting = _time_greeting(now)
    date_str = now.strftime("%a %d %b")
    weather = _compact_weather(_strip_terminal_sir(await get_weather()))
    calendar = get_today_event_summary(now, compact=True)
    task_str = _format_tasks([_compact_task(str(task)) for task in tasks])

    schedule_summary = ""
    if owner_id is not None:
        from app.scheduling.service import get_service
        schedule_summary = " " + get_service().brief_summary(owner_id)
    return f"{greeting} {date_str}. {weather}. Calendar: {calendar}. Focus: {task_str}.{schedule_summary}"


def load_brief_config(path: Path = BRIEF_CONFIG_PATH) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Brief config unavailable: %s", exc)
        return {"daily_tasks": [], "location": "London", "wake_time": "05:30"}

    if not isinstance(data, dict):
        return {"daily_tasks": [], "location": "London", "wake_time": "05:30"}
    return data


def _time_greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Morning, sir."
    if now.hour < 17:
        return "Afternoon, sir."
    return "Good evening, sir."


def _format_tasks(tasks: list[str]) -> str:
    clean_tasks = [task.strip() for task in tasks if task.strip()]
    if not clean_tasks:
        return "no configured tasks"
    if len(clean_tasks) == 1:
        return clean_tasks[0]
    return ", ".join(clean_tasks)


def _strip_terminal_sir(text: str) -> str:
    clean_text = text.strip()
    for suffix in (", sir.", ", sir"):
        if clean_text.lower().endswith(suffix):
            return clean_text[: -len(suffix)].rstrip() + "."
    return clean_text


def _compact_weather(text: str) -> str:
    compact = text.strip().rstrip(".")
    compact = compact.replace("Moderate drizzle", "Drizzle")
    compact = compact.replace("Light drizzle", "Drizzle")
    compact = compact.replace("Dense drizzle", "Drizzle")
    compact = compact.replace(" degrees", "")
    return compact


def _compact_task(task: str) -> str:
    compact = task.strip()
    replacements = {
        "5 job applications": "5 apps",
        "Rasylon emails": "Rasylon",
        "JARVIS Sprint 2": "Sprint 2",
        "20 pages reading": "reading",
        "Linear algebra": "algebra",
    }
    return replacements.get(compact, compact)
