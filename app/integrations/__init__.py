"""External service integrations."""

from app.integrations.search import web_search
from app.integrations.weather import get_weather
from app.integrations.brief import get_morning_brief
from app.integrations.calendar import get_today_calendar
from app.integrations.ide import open_antigravity, open_file, open_vscode, run_server

__all__ = [
    "get_morning_brief",
    "get_today_calendar",
    "get_weather",
    "open_antigravity",
    "open_file",
    "open_vscode",
    "run_server",
    "web_search",
]
