"""External service integrations."""

from app.integrations.search import web_search
from app.integrations.weather import get_weather
from app.integrations.brief import get_morning_brief
from app.integrations.calendar import get_today_calendar

__all__ = ["get_morning_brief", "get_today_calendar", "get_weather", "web_search"]
