from dataclasses import dataclass
from datetime import datetime

from app.integrations.brief import get_morning_brief
from app.integrations.search import web_search
from app.integrations.weather import get_weather


@dataclass(frozen=True)
class ToolResult:
    name: str
    content: str


class ToolRouter:
    async def route(self, message: str) -> ToolResult | None:
        normalized = self._normalize(message)

        if self._is_time_request(normalized):
            return ToolResult(name="time", content=get_current_time())
        if self._is_date_request(normalized):
            return ToolResult(name="date", content=get_current_date())
        if self._is_weather_request(normalized):
            return ToolResult(name="weather", content=await get_weather())
        if self._is_morning_brief_request(normalized):
            return ToolResult(name="morning_brief", content=await get_morning_brief())
        search_query = self._extract_search_query(normalized)
        if search_query:
            return ToolResult(name="search", content=await web_search(search_query))

        return None

    @staticmethod
    def _normalize(message: str) -> str:
        lowered = message.lower().strip()
        for char in ",.?!":
            lowered = lowered.replace(char, " ")
        words = [word for word in lowered.split() if word not in {"jarvis", "please"}]
        return " ".join(words)

    @staticmethod
    def _is_time_request(message: str) -> bool:
        return (
            "what time is it" in message
            or message in {"time", "the time"}
            or message.startswith("tell me the time")
        )

    @staticmethod
    def _is_date_request(message: str) -> bool:
        return (
            "today's date" in message
            or "todays date" in message
            or "what date is it" in message
            or "what is the date" in message
        )

    @staticmethod
    def _is_weather_request(message: str) -> bool:
        return (
            "weather" in message
            or "what's it like outside" in message
            or "whats it like outside" in message
            or "what is it like outside" in message
            or "should i bring a jacket" in message
            or "temperature" in message
        )

    @staticmethod
    def _is_morning_brief_request(message: str) -> bool:
        return (
            "good morning" in message
            or "good afternoon" in message
            or "good evening" in message
            or "morning brief" in message
            or "what's my plan" in message
            or "whats my plan" in message
            or "what is my plan" in message
            or "what should i focus on" in message
        )

    @staticmethod
    def _extract_search_query(message: str) -> str | None:
        prefixes = (
            "search for ",
            "look up ",
            "find out ",
            "what is ",
            "who is ",
            "tell me about ",
        )
        for prefix in prefixes:
            if message.startswith(prefix):
                query = message.removeprefix(prefix).strip()
                return query or None
        return None


def get_current_time(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"It's {current:%H:%M}, sir."


def get_current_date(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"{current:%A} the {_ordinal(current.day)} of {current:%B}, sir."


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"
