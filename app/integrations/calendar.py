from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_PATH = PROJECT_ROOT / "data" / "calendar" / "events.json"


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    event_date: date
    start_time: str | None = None
    end_time: str | None = None


async def get_today_calendar(now: datetime | None = None) -> str:
    current = now or datetime.now()
    events = get_events_for_date(current.date())
    if not events:
        return "Your calendar is clear today, sir."

    event_text = ", ".join(_format_event(event) for event in events)
    return f"Today you have {event_text}, sir."


def get_today_event_summary(now: datetime | None = None, compact: bool = False) -> str:
    current = now or datetime.now()
    events = get_events_for_date(current.date())
    if not events:
        return "calendar clear"
    if compact:
        return ", ".join(_format_event_compact(event) for event in events)
    return ", ".join(_format_event(event, include_sir=False) for event in events)


def get_events_for_date(target_date: date) -> list[CalendarEvent]:
    events = _load_events()
    todays_events = [event for event in events if event.event_date == target_date]
    return sorted(todays_events, key=lambda event: event.start_time or "99:99")


def _load_events(path: Path = CALENDAR_PATH) -> list[CalendarEvent]:
    try:
        with path.open("r", encoding="utf-8") as calendar_file:
            payload = json.load(calendar_file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Calendar file unavailable: %s", exc)
        return []

    raw_events = payload.get("events") if isinstance(payload, dict) else []
    if not isinstance(raw_events, list):
        return []

    events = []
    for item in raw_events:
        event = _parse_event(item)
        if event is not None:
            events.append(event)
    return events


def _parse_event(item: Any) -> CalendarEvent | None:
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    date_value = str(item.get("date") or "").strip()
    if not title or not date_value:
        return None

    try:
        event_date = date.fromisoformat(date_value)
    except ValueError:
        logger.error("Calendar event has invalid date: %s", item)
        return None

    return CalendarEvent(
        title=title,
        event_date=event_date,
        start_time=_clean_time(item.get("start_time")),
        end_time=_clean_time(item.get("end_time")),
    )


def _clean_time(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        logger.error("Calendar event has invalid time: %s", value)
        return None
    return text


def _format_event(event: CalendarEvent, include_sir: bool = True) -> str:
    if event.start_time and event.end_time:
        return f"{event.title} from {_spoken_time(event.start_time)} to {_spoken_time(event.end_time)}"
    if event.start_time:
        return f"{event.title} at {_spoken_time(event.start_time)}"
    return event.title if not include_sir else event.title


def _format_event_compact(event: CalendarEvent) -> str:
    if event.start_time:
        return f"{_compact_title(event.title)} at {_spoken_time(event.start_time)}"
    return _compact_title(event.title)


def _compact_title(title: str) -> str:
    replacements = {
        "JARVIS Sprint 2": "Sprint 2",
        "Job applications": "jobs",
        "Linear algebra review": "algebra",
    }
    return replacements.get(title, title)


def _spoken_time(value: str) -> str:
    return datetime.strptime(value, "%H:%M").strftime("%H:%M")
