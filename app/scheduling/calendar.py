"""Local calendar adapter. No invitations or external-provider writes."""
from datetime import datetime, timedelta, timezone
from app.scheduling.timeparse import Clarification, next_occurrence, zone, localize


def occurrences(job: dict, start: datetime, end: datetime):
    when = datetime.fromtimestamp(job['due'], timezone.utc)
    duration = timedelta(minutes=job['duration'])
    for _ in range(20000):
        if when >= end:
            return
        if when + duration > start:
            yield {'id': job['id'], 'title': job['title'], 'start': when, 'end': when + duration, 'source': 'jarvis'}
        if not job['recurrence']:
            return
        when = next_occurrence(when, job['recurrence'], job['timezone'])
    raise Clarification('This recurrence range is too large. Please choose a shorter range.')


class LocalCalendar:
    def __init__(self, store):
        self.store = store

    def between(self, owner, start, end, tz_name, exclude=''):
        events = []
        for job in self.store.list(owner, 'event'):
            if job['id'] != exclude and job['status'] == 'active':
                events.extend(occurrences(job, start, end))
        # The existing JSON adapter remains a read-only source of calendar events.
        from app.integrations.calendar import get_events_for_date, CALENDAR_PATH, CalendarUnavailable
        if not CALENDAR_PATH.is_file():
            return sorted(events, key=lambda e: e['start'])
        day = start.astimezone(zone(tz_name)).date()
        last = end.astimezone(zone(tz_name)).date()
        while day <= last:
            try:
                legacy = get_events_for_date(day, strict=True)
            except CalendarUnavailable as exc:
                raise Clarification(str(exc) + ' Calendar conflicts cannot be verified.') from None
            for event in legacy:
                begin = localize(datetime.fromisoformat(f'{day}T{event.start_time or "00:00"}'), zone(tz_name))
                finish = localize(datetime.fromisoformat(f'{day}T{event.end_time}'), zone(tz_name)) if event.end_time else begin + timedelta(minutes=60 if event.start_time else 1440)
                if finish > start and begin < end:
                    events.append({'id': 'legacy', 'title': event.title, 'start': begin, 'end': finish, 'source': 'local_json'})
            day += timedelta(days=1)
        return sorted(events, key=lambda e: e['start'])

    def validate(self, owner, schedule, tz_name, duration, exclude=''):
        start = schedule.at
        # Bound conflict expansion; recurring local calendars use a one-year planning window.
        end = start + timedelta(days=366 if schedule.recurrence else 1)
        proposed = {'id': '', 'title': '', 'due': start.timestamp(), 'duration': duration,
                    'recurrence': schedule.recurrence, 'timezone': tz_name}
        existing = self.between(owner, start, end + timedelta(minutes=duration), tz_name, exclude)
        for item in occurrences(proposed, start, end):
            for event in existing:
                if item['start'] < event['end'] and item['end'] > event['start']:
                    raise Clarification(f'That overlaps with {event["title"]}. Choose another time.')

    def free(self, owner, day, duration, tz_name):
        tz = zone(tz_name)
        begin = localize(datetime.combine(day, datetime.min.time()).replace(hour=9), tz)
        end = localize(datetime.combine(day, datetime.min.time()).replace(hour=17), tz)
        now = datetime.now(timezone.utc)
        begin = max(begin, now)
        for event in self.between(owner, begin, end, tz_name):
            if begin + timedelta(minutes=duration) <= event['start']:
                return begin
            begin = max(begin, event['end'])
        return begin if begin + timedelta(minutes=duration) <= end else None
