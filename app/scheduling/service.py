from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from app.scheduling.calendar import LocalCalendar
from app.scheduling.bold import BoldAdapter, BoldError, UnconfiguredBold
from app.scheduling.models import Command, Intent
from app.scheduling.store import Store, utcnow
from app.scheduling.timeparse import Clarification, Schedule, parse_when, zone


class SchedulingService:
    def __init__(self, store: Store, timezone_name='Europe/London', bold: BoldAdapter | None = None):
        self.store = store
        self.timezone = timezone_name
        zone(timezone_name)
        self.calendar = LocalCalendar(store)
        self.bold = bold or UnconfiguredBold()

    def execute(self, command: Command, owner: str, session='default', *, expected_version=None, prepared=None):
        try:
            return self._execute(command, owner, session, expected_version, prepared)
        except Clarification as exc:
            return {'status': 'clarification_required', 'message': str(exc)}
        except BoldError as exc:
            return {'status': 'unavailable', 'message': str(exc)}

    def _execute(self, c, owner, session, expected_version, prepared):
        if c.intent.value.startswith('BOLD_'):
            return self._execute_bold(c, owner, session)
        if c.intent == Intent.CONFIRM:
            with self.store.transaction() as db:
                if c.confirmation_id == 'latest':
                    candidates = db.execute('SELECT id FROM confirmations WHERE owner=? AND session=? AND expires>?', (owner, session, utcnow().timestamp())).fetchall()
                    if len(candidates) != 1:
                        raise Clarification('There is no single pending change. Please use the exact confirmation ID from its preview.')
                    c = c.model_copy(update={'confirmation_id': candidates[0]['id']})
                row = db.execute('SELECT * FROM confirmations WHERE id=? AND owner=? AND session=? AND expires>?',
                                 (c.confirmation_id, owner, session, utcnow().timestamp())).fetchone()
                if not row:
                    raise Clarification('That confirmation is missing, expired, or belongs to another session.')
                payload = json.loads(row['payload'])
                db.execute('DELETE FROM confirmations WHERE id=?', (row['id'],))
            original = Command.model_validate(payload['command'])
            original.confirmed = True
            schedule = Schedule(datetime.fromisoformat(payload['at']), payload['recurrence']) if payload.get('at') else None
            return self.execute(original, owner, session, expected_version=payload.get('version'), prepared=schedule)
        if c.target == 'clarify':
            raise Clarification('Please specify the action, title and an exact time. Example: remind me tomorrow at 9 AM to call David.')
        if c.target == 'unsupported_action':
            raise Clarification('Approved automation actions are daily briefing and reminder summary. No arbitrary commands or external communications can be automated.')
        tz = c.timezone or self.timezone
        zone(tz)
        name = c.intent.value
        kind = 'automation' if 'AUTOMATION' in name else 'event' if 'CALENDAR' in name else 'reminder'
        if name.startswith('LIST_'):
            if kind == 'event':
                begin, end = self.date_range(c.when, tz)
                records = self.calendar.between(owner, begin, end, tz)
                items = [{**r, 'start': r['start'].isoformat(), 'end': r['end'].isoformat()} for r in records]
                return {'status': 'ok', 'items': items, 'message': '\n'.join(f"{r['title']} — {r['start'].astimezone(zone(tz)).isoformat()} [{r['id']}]" for r in records) or 'No local calendar events in that range. External calendars are not connected.'}
            rows = self.store.list(owner, kind)
            if c.when == 'today':
                begin, end = self.date_range('today', tz)
                rows = [r for r in rows if begin.timestamp() <= r['due'] < end.timestamp()]
            return {'status': 'ok', 'items': rows, 'message': '\n'.join(self.describe(r) for r in rows) or f'No {kind}s in that range.'}
        if c.intent == Intent.FIND_FREE_TIME:
            if c.when not in ('today', 'tomorrow'):
                raise Clarification('For which day should I look for a free slot?')
            begin, _ = self.date_range(c.when, tz)
            slot = self.calendar.free(owner, begin.date(), c.duration_minutes, tz)
            return {'status': 'ok', 'message': f'Local calendar has a {c.duration_minutes}-minute slot at {slot.isoformat()}.' if slot else 'No free slot between 09:00 and 17:00 in the local calendar.'}
        if name.startswith('CREATE_'):
            if not c.title.strip():
                raise Clarification('What should I call this reminder, event, or automation?')
            fingerprint = hashlib.sha256(json.dumps([c.model_dump(mode='json', exclude={'confirmed', 'idempotency_key'}), tz], sort_keys=True).encode()).hexdigest()
            existing = self.store.existing_request(owner, c.idempotency_key, fingerprint)
            if existing:
                return {'status': 'existing', 'item': existing, 'message': 'This request was already saved. ' + self.describe(existing)}
            schedule = prepared or parse_when(c.when, tz)
            if schedule.at <= utcnow():
                raise Clarification('That time has passed. Please choose a new time.')
            if kind == 'event':
                self.calendar.validate(owner, schedule, tz, c.duration_minutes)
                if not c.confirmed:
                    return self.confirm(c, owner, session, schedule=schedule)
                if isinstance(self.bold, UnconfiguredBold):
                    return {'status': 'unavailable', 'message': 'Bold calendar is not configured, so the event was not saved.'}
                end_at = schedule.at + timedelta(minutes=c.duration_minutes)
                remote = self.bold.create_record(
                    'note',
                    {
                        'title': c.title.strip(),
                        'bodyV2': f'Scheduled for {schedule.at.isoformat()}–{end_at.isoformat()} ({c.duration_minutes} minutes).',
                    },
                    c.idempotency_key or uuid4().hex,
                )
            row = self.store.create(owner, kind, c.title, schedule, tz, c.duration_minutes, c.action if kind == 'automation' else '', c.idempotency_key, fingerprint, (lambda: self.calendar.validate(owner, schedule, tz, c.duration_minutes)) if kind == 'event' else None)
            delivery = ' Notification channel: in-app inbox; device delivery is not configured.' if kind != 'event' else ' Saved to the local calendar; no invitations sent.'
            if kind == 'event':
                remote_id = remote.id
                delivery = f' Scheduled in Bold Notes (record {remote_id}).'
            return {'status': 'created', 'item': row, 'message': self.describe(row) + delivery}
        job = self.store.find(owner, kind, c.target)
        if expected_version is not None and job['version'] != expected_version:
            raise Clarification('This item changed after the preview. Please request the change again.')
        operation = name.split('_')[0].lower()
        operation = {'delete': 'cancel'}.get(operation, operation)
        schedule = prepared
        if operation in ('update', 'snooze'):
            when = c.when
            if when.lower() in ('tomorrow', 'today', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'):
                old = datetime.fromtimestamp(job['due'], timezone.utc).astimezone(zone(job['timezone']))
                when += f' at {old:%H:%M}'
            schedule = schedule or parse_when(when, job['timezone'])
            if schedule.at <= utcnow():
                raise Clarification('That time has passed. Please choose a future time.')
            if operation == 'snooze' and schedule.recurrence:
                raise Clarification('Snooze needs a one-time future date or interval.')
            if kind == 'event':
                self.calendar.validate(owner, schedule, job['timezone'], job['duration'], job['id'])
        if not c.confirmed:
            resolved = c.model_copy(update={'target': job['id']})
            return self.confirm(resolved, owner, session, job, schedule)
        row = self.store.mutate(owner, job, operation, schedule, (lambda: self.calendar.validate(owner, schedule, job['timezone'], job['duration'], job['id'])) if kind == 'event' and schedule else None)
        return {'status': 'updated', 'item': row, 'message': self.describe(row)}

    def confirm(self, c, owner, session, job=None, schedule=None):
        confirmation_id = uuid4().hex[:16]
        payload = {'command': c.model_dump(mode='json'), 'version': job['version'] if job else None,
                   'at': schedule.at.isoformat() if schedule else None,
                   'recurrence': schedule.recurrence if schedule else None}
        with self.store.transaction() as db:
            db.execute('DELETE FROM confirmations WHERE expires<=?', (utcnow().timestamp(),))
            db.execute('INSERT INTO confirmations VALUES(?,?,?,?,?)',
                       (confirmation_id, owner, session, json.dumps(payload), utcnow().timestamp() + 600))
            self.store.audit(db, owner, job['id'] if job else None, 'confirmation_requested', c.intent.value)
        title = job['title'] if job else c.title
        when = f" at {schedule.at.astimezone(zone(c.timezone or (job['timezone'] if job else self.timezone))).isoformat()}" if schedule else ''
        repeat = f', repeating {schedule.recurrence}' if schedule and schedule.recurrence else ''
        duration = f', {c.duration_minutes if not job else job["duration"]} minutes' if 'CALENDAR' in c.intent.value else ''
        return {'status': 'confirmation_required', 'confirmation_id': confirmation_id,
                'message': f'{c.intent.value}: {title}{when}{repeat}{duration}. Confirm with “confirm {confirmation_id}” within 10 minutes.'}

    def _execute_bold(self, command, owner, session):
        intent = command.intent
        if isinstance(self.bold, UnconfiguredBold):
            return {'status': 'unavailable', 'message': 'Bold is not configured for this service instance. No CRM record was changed.'}
        if intent == Intent.BOLD_LIST_TASKS:
            result = self.bold.list_records('task', limit=50)
            rows = result['records']
            return {'status': 'ok', 'items': rows, 'message': '\n'.join(self._bold_description(row) for row in rows) or 'No Bold tasks found.'}
        if intent == Intent.BOLD_SEARCH_NOTES:
            query = (command.target or command.title).strip().casefold()
            result = self.bold.list_records('note', limit=100)
            rows = [row for row in result['records'] if not query or query in str(row).casefold()]
            return {'status': 'ok', 'items': rows, 'message': '\n'.join(self._bold_description(row) for row in rows) or 'No matching Bold notes found.'}
        if intent == Intent.BOLD_SYNC:
            return {'status': 'unavailable', 'message': 'Bold sync requires an explicitly selected local item and remote record. No records were changed.'}
        if intent in {Intent.BOLD_CREATE_NOTE, Intent.BOLD_CREATE_TASK}:
            if not command.title.strip():
                raise Clarification('What should I create in Bold?')
            if not command.confirmed:
                return self.confirm(command, owner, session)
            record_type = 'note' if intent == Intent.BOLD_CREATE_NOTE else 'task'
            payload = {'title': command.title.strip()}
            if record_type == 'note':
                payload['bodyV2'] = command.title.strip()
            elif command.when:
                schedule = parse_when(command.when, command.timezone or self.timezone)
                payload.update({'dueAt': schedule.at.isoformat(timespec='milliseconds').replace('+00:00', 'Z'), 'status': 'TODO'})
            record = self.bold.create_record(record_type, payload, command.idempotency_key or uuid4().hex)
            return {'status': 'created', 'item': record.raw or {'id': record.id, 'title': record.title}, 'message': f'Created the Bold {record_type} {record.id}.'}
        if intent in {Intent.BOLD_COMPLETE_TASK, Intent.BOLD_UPDATE_TASK}:
            target = command.target or command.title
            record = self._find_bold_task(target)
            if not command.confirmed:
                preview = command.model_copy(update={'target': record.id, 'title': record.title})
                return self.confirm(preview, owner, session)
            payload = {'status': 'DONE'} if intent == Intent.BOLD_COMPLETE_TASK else self._bold_update_payload(command)
            updated = self.bold.update_record('task', record.id, payload, record.version)
            return {'status': 'updated', 'item': updated.raw or {'id': updated.id, 'title': updated.title}, 'message': f'Updated Bold task {updated.id}.'}
        return {'status': 'unavailable', 'message': 'That Bold operation is not enabled.'}

    def _find_bold_task(self, target):
        result = self.bold.list_records('task', limit=100)
        matches = [row for row in result['records'] if str(row.get('id', '')) == target or target.casefold() in str(row.get('title', '')).casefold()]
        if len(matches) != 1:
            raise Clarification('Specify one exact Bold task title or ID; the target is missing or ambiguous.')
        return self.bold.get_record('task', str(matches[0]['id']))

    @staticmethod
    def _bold_update_payload(command):
        if not command.when:
            raise Clarification('What due date and time should the Bold task use?')
        schedule = parse_when(command.when, command.timezone or 'Europe/London')
        return {'dueAt': schedule.at.isoformat(timespec='milliseconds').replace('+00:00', 'Z')}

    @staticmethod
    def _bold_description(row):
        record_id = row.get('id', row.get('recordId', 'unknown'))
        title = row.get('title', row.get('name', '(untitled)'))
        status = row.get('status', '')
        return f"{title} [{record_id}]" + (f" — {status}" if status else '')

    @staticmethod
    def describe(row):
        when = datetime.fromtimestamp(row['due'], timezone.utc).astimezone(zone(row['timezone']))
        recurrence = f"; repeats {row['recurrence']}" if row['recurrence'] else ''
        return f"{row['title']} — {when.isoformat()} ({row['timezone']}; {row['status']}{recurrence}) [{row['id']}]"

    @staticmethod
    def date_range(text, tz):
        now = utcnow().astimezone(zone(tz))
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if text == 'tomorrow':
            start += timedelta(days=1)
        if text == 'next week':
            start += timedelta(days=7 - start.weekday())
        return start, start + timedelta(days=7 if text == 'next week' else 1)

    def brief_summary(self, owner):
        begin, end = self.date_range('today', self.timezone)
        reminders = self.store.list(owner, 'reminder')
        today = [r for r in reminders if begin.timestamp() <= r['due'] < end.timestamp()]
        overdue = [r for r in reminders if r['due'] < utcnow().timestamp() and r['status'] == 'active']
        events = self.calendar.between(owner, begin, end, self.timezone)
        return f'Local schedule: {len(events)} calendar events, {len(today)} pending reminders today, {len(overdue)} overdue reminders.'


@lru_cache(maxsize=1)
def get_service():
    root = Path(__file__).resolve().parents[2]
    from app.core.config import get_settings
    from app.scheduling.bold import BoldRestClient
    settings = get_settings()
    bold = BoldRestClient(settings.bold_api_base_url, settings.bold_api_token, settings.bold_request_timeout_seconds) if settings.bold_api_token else UnconfiguredBold()
    return SchedulingService(Store(os.getenv('JARVIS_SCHEDULER_DB', str(root / 'data/scheduling.sqlite3'))),
                             os.getenv('JARVIS_TIMEZONE', 'Europe/London'), bold=bold)
