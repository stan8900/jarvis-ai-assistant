from dataclasses import dataclass
from datetime import datetime

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
            return ToolResult(name="morning_brief", content=get_morning_brief())

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
            "morning brief" in message
            or "what's my plan" in message
            or "whats my plan" in message
            or "what is my plan" in message
        )


def get_current_time(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"It's {current:%H:%M}, sir."


def get_current_date(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"{current:%A} the {_ordinal(current.day)} of {current:%B}, sir."


def get_morning_brief() -> str:
    return "Morning brief not yet configured, sir."


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"
