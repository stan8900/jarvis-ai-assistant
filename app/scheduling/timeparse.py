"""Conservative natural-language dates with deterministic IANA/DST validation."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


class Clarification(ValueError):
    pass


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise Clarification('Please supply a valid IANA timezone, such as Europe/London.') from None


def localize(value: datetime, tz: ZoneInfo) -> datetime:
    """Reject nonexistent and ambiguous wall times rather than choosing a fold."""
    a, b = value.replace(tzinfo=tz, fold=0), value.replace(tzinfo=tz, fold=1)
    valid = [d for d in (a, b) if d.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == value]
    if not valid:
        raise Clarification('That local time does not exist because of daylight saving. Choose another time.')
    if len({d.utcoffset() for d in valid}) > 1:
        raise Clarification('That time occurs twice because of daylight saving. Supply an ISO timestamp with an explicit offset.')
    return valid[0]


@dataclass(frozen=True)
class Schedule:
    at: datetime
    recurrence: str | None = None


def parse_when(expression: str, timezone_name: str, now: datetime | None = None) -> Schedule:
    tz = zone(timezone_name)
    current = (now or datetime.now(UTC)).astimezone(tz)
    text = expression.lower().strip().rstrip('.?!').strip()
    text = re.sub(r'^(?:on|at)\s+', '', text)
    relative = re.fullmatch(r'in (\d+) (minute|hour|day|week)s?', text)
    interval = re.fullmatch(r'every (\d+) (minute|hour)s?', text)
    if relative or interval:
        match = relative or interval
        amount = int(match[1])
        if not 1 <= amount <= 525600:
            raise Clarification('Choose a positive interval up to 525600 units.')
        seconds = amount * {'minute': 60, 'hour': 3600, 'day': 86400, 'week': 604800}[match[2]]
        return Schedule(current.astimezone(UTC) + timedelta(seconds=seconds), f'interval:{seconds}' if interval else None)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        raise Clarification('What exact time on that date? Please include a time and timezone.')
    try:
        iso = datetime.fromisoformat(expression.strip().replace('Z', '+00:00'))
    except ValueError:
        iso = None
    if iso is not None:
        value = localize(iso, tz) if iso.tzinfo is None else iso.astimezone(tz)
        if value.astimezone(UTC) <= current.astimezone(UTC):
            raise Clarification('That date is in the past. Choose a future date and time.')
        return Schedule(value.astimezone(UTC))
    # Never assign an implicit hour to morning/evening or a bare date.
    clock = re.search(r'(?:\bat\s+|^)(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$', text)
    if not clock:
        raise Clarification('What exact date and time? For example: tomorrow at 9 AM, in 30 minutes, or every Monday at 9 AM.')
    hour, minute, meridiem = int(clock[1]), int(clock[2] or 0), clock[3]
    if minute > 59 or hour > 23 or (meridiem and not 1 <= hour <= 12):
        raise Clarification('Please give a valid time.')
    if not meridiem and clock[2] is None:
        raise Clarification('Do you mean AM or PM? Alternatively use a 24-hour time such as 18:00.')
    if meridiem:
        hour = hour % 12 + (12 if meridiem == 'pm' else 0)
    day_text = text[:clock.start()].strip()
    recurrence = None
    target = current.date()
    if day_text in ('every day', 'daily', 'every morning', 'every evening'):
        recurrence = 'daily'
    elif day_text in ('every weekday', 'weekdays'):
        recurrence = 'weekdays'
    elif match := re.fullmatch(r'every (' + '|'.join(WEEKDAYS) + ')', day_text):
        recurrence = 'weekly'
        target += timedelta(days=(WEEKDAYS.index(match[1]) - target.weekday()) % 7)
    elif match := re.fullmatch(r'every month on (\d{1,2})(?:st|nd|rd|th)?', day_text):
        day = int(match[1])
        if not 1 <= day <= 31:
            raise Clarification('Choose a day of the month from 1 to 31.')
        recurrence = f'monthly:{day}'
        target = target.replace(day=min(day, calendar.monthrange(target.year, target.month)[1]))
    elif day_text == 'tomorrow':
        target += timedelta(days=1)
    elif day_text in WEEKDAYS or day_text.removeprefix('next ') in WEEKDAYS:
        weekday = WEEKDAYS.index(day_text.removeprefix('next '))
        target += timedelta(days=(weekday - target.weekday()) % 7 or 7)
    elif day_text not in ('', 'today', 'tonight'):
        try:
            target = datetime.strptime(day_text, '%Y-%m-%d').date()
        except ValueError:
            raise Clarification('Please specify a date, such as tomorrow, Friday, or 2026-12-01, and an exact time.') from None
    naive = datetime.combine(target, datetime.min.time()).replace(hour=hour, minute=minute)
    value = localize(naive, tz)
    if recurrence == 'weekdays':
        while value.weekday() > 4:
            value = localize(value.replace(tzinfo=None) + timedelta(days=1), tz)
    if value.astimezone(UTC) <= current.astimezone(UTC):
        if recurrence:
            value = next_occurrence(value, recurrence, timezone_name)
        elif day_text == '':
            value = localize(naive + timedelta(days=1), tz)
        else:
            raise Clarification('That time is in the past. Choose a future time.')
    return Schedule(value.astimezone(UTC), recurrence)


def next_occurrence(previous: datetime, rule: str, timezone_name: str) -> datetime:
    if rule.startswith('interval:'):
        return previous.astimezone(UTC) + timedelta(seconds=int(rule.split(':')[1]))
    tz = zone(timezone_name)
    value = previous.astimezone(tz).replace(tzinfo=None)
    if rule.startswith('monthly:'):
        month = value.month % 12 + 1
        year = value.year + (value.month == 12)
        day = min(int(rule.split(':')[1]), calendar.monthrange(year, month)[1])
        value = value.replace(year=year, month=month, day=day)
    else:
        value += timedelta(days=7 if rule == 'weekly' else 1)
        if rule == 'weekdays':
            while value.weekday() > 4:
                value += timedelta(days=1)
    # Ambiguous/nonexistent recurring occurrences stop visibly; never silently move them.
    return localize(value, tz).astimezone(UTC)
