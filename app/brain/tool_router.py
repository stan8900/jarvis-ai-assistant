from dataclasses import dataclass
from datetime import datetime

from app.integrations.brief import get_morning_brief
from app.integrations.calendar import get_today_calendar
from app.integrations.ide import open_antigravity, open_file, open_vscode, run_server
from app.integrations.search import web_search
from app.integrations.weather import get_weather
from app.memory.long_term_memory import LongTermMemory


@dataclass(frozen=True)
class ToolResult:
    name: str
    content: str


class ToolRouter:
    async def route(
        self,
        message: str,
        long_term_memory: LongTermMemory | None = None,
    ) -> ToolResult | None:
        normalized = self._normalize(message)

        remember_fact = self._extract_remember_fact(normalized)
        if remember_fact is not None:
            key, value = remember_fact
            if long_term_memory is not None:
                long_term_memory.remember(key, value)
            return ToolResult(name="memory", content=f"Noted, sir. {value}.")
        if self._is_recall_all_request(normalized):
            return ToolResult(
                name="memory",
                content=self._format_recalled_facts(long_term_memory),
            )
        if self._is_time_request(normalized):
            return ToolResult(name="time", content=get_current_time())
        if self._is_date_request(normalized):
            return ToolResult(name="date", content=get_current_date())
        ide_result = self._route_ide(normalized)
        if ide_result is not None:
            return ide_result
        if self._is_weather_request(normalized):
            return ToolResult(name="weather", content=await get_weather())
        if self._is_morning_brief_request(normalized):
            return ToolResult(name="morning_brief", content=await get_morning_brief())
        if self._is_calendar_request(normalized):
            return ToolResult(name="calendar", content=await get_today_calendar())
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
    def _is_calendar_request(message: str) -> bool:
        return (
            "calendar" in message
            or "schedule today" in message
            or "what meetings do i have" in message
            or "what's on my schedule" in message
            or "whats on my schedule" in message
            or "what is on my schedule" in message
            or "what's on my calendar" in message
            or "whats on my calendar" in message
            or "what is on my calendar" in message
        )

    @staticmethod
    def _route_ide(message: str) -> ToolResult | None:
        if message in {"open vs code", "open vscode", "launch vs code", "launch vscode"}:
            return ToolResult(name="ide", content=open_vscode())
        if message in {
            "open antigravity",
            "open antigravity ide",
            "launch antigravity",
            "launch antigravity ide",
        }:
            return ToolResult(name="ide", content=open_antigravity())
        if message in {"start the server", "run the server", "start server", "run server"}:
            return ToolResult(name="ide", content=run_server())

        filename = _extract_open_filename(message)
        if filename:
            return ToolResult(name="ide", content=open_file(filename))
        return None

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

    @staticmethod
    def _extract_remember_fact(message: str) -> tuple[str, str] | None:
        prefixes = (
            "remember that ",
            "don't forget ",
            "dont forget ",
            "note that ",
        )
        for prefix in prefixes:
            if not message.startswith(prefix):
                continue
            fact = message.removeprefix(prefix).strip()
            if not fact:
                return None
            return _fact_key_from_text(fact), _format_fact_value(fact)
        return None

    @staticmethod
    def _is_recall_all_request(message: str) -> bool:
        return (
            "what do you know about me" in message
            or "what do you remember about me" in message
            or "what have you remembered" in message
        )

    @staticmethod
    def _format_recalled_facts(long_term_memory: LongTermMemory | None) -> str:
        if long_term_memory is None:
            return "I do not have long-term memory connected, sir."
        facts = long_term_memory.recall_all(limit=8)
        if not facts:
            return "I have no stored facts yet, sir."
        fact_text = "; ".join(fact.value for fact in facts)
        return f"I remember: {fact_text}, sir."


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


def _fact_key_from_text(text: str) -> str:
    clean = text.strip().lower()
    replacements = (
        ("my ", ""),
        ("i ", ""),
        ("am ", ""),
        ("is ", ""),
    )
    for old, new in replacements:
        if clean.startswith(old):
            clean = clean.replace(old, new, 1)
    splitters = (" is ", " are ", " am ", " at ", " every ", " daily")
    for splitter in splitters:
        if splitter in clean:
            return clean.split(splitter, 1)[0].strip()
    return " ".join(clean.split()[:6])


def _format_fact_value(text: str) -> str:
    clean = text.strip()
    if not clean:
        return clean
    if clean.lower().startswith("my "):
        clean = clean[3:].strip()
    return clean[0].upper() + clean[1:]


def _extract_open_filename(message: str) -> str | None:
    prefixes = (
        "open file ",
        "open the file ",
        "open the ",
        "open ",
    )
    for prefix in prefixes:
        if message.startswith(prefix):
            target = message.removeprefix(prefix).strip()
            if target not in {"vs code", "vscode"}:
                return target or None
    return None
