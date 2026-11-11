from __future__ import annotations

import hashlib
import json
import re
from zoneinfo import ZoneInfo
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.scheduling.timeparse import Clarification, Schedule, next_occurrence


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: str):
        self.path = str(Path(path).expanduser().resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript((Path(__file__).parent / 'migrations/001_initial.sql').read_text())
        Path(self.path).chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def audit(db, owner, job_id, operation, detail=''):
        db.execute('INSERT INTO audit(owner,job_id,operation,created,detail) VALUES(?,?,?,?,?)',
                   (owner, job_id, operation, utcnow().timestamp(), detail))

    def create(self, owner: str, kind: str, title: str, schedule: Schedule, tz: str,
               duration: int = 60, action: str = '', key: str | None = None, request_fingerprint: str | None = None, calendar_validator=None) -> dict:
        content = json.dumps([kind, title.strip(), schedule.at.timestamp(), tz, schedule.recurrence, duration, action])
        fingerprint = request_fingerprint or hashlib.sha256(content.encode()).hexdigest()
        create_key = key or fingerprint
        now = utcnow().timestamp()
        with self.transaction() as db:
            existing = db.execute('SELECT * FROM jobs WHERE owner=? AND create_key=?', (owner, create_key)).fetchone()
            if existing:
                # A reused explicit key is safe only for the same immutable creation payload.
                creation = db.execute("SELECT detail FROM audit WHERE job_id=? AND operation='create'", (existing['id'],)).fetchone()
                if creation and creation['detail'] != fingerprint:
                    raise Clarification('That idempotency key was already used for a different request.')
                return dict(existing)
            if kind == 'event':
                if calendar_validator:
                    calendar_validator()
                self.check_conflicts(db, owner, schedule.at.timestamp(), duration)
            job_id = uuid4().hex
            db.execute('INSERT INTO jobs(id,owner,kind,title,due,timezone,recurrence,duration,action,create_key,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (job_id, owner, kind, title.strip(), schedule.at.timestamp(), tz, schedule.recurrence, duration, action, create_key, now, now))
            self.audit(db, owner, job_id, 'create', fingerprint)
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    def existing_request(self, owner, key, fingerprint):
        if not key:
            return None
        with self.connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE owner=? AND create_key=?', (owner, key)).fetchone()
            if row:
                original = db.execute("SELECT detail FROM audit WHERE job_id=? AND operation='create'", (row['id'],)).fetchone()
                if not original or original['detail'] != fingerprint:
                    raise Clarification('That idempotency key was already used for a different request.')
                return dict(row)
        return None

    @staticmethod
    def check_conflicts(db, owner, due, duration, exclude=''):
        clash = db.execute("SELECT title FROM jobs WHERE owner=? AND kind='event' AND status='active' AND id!=? AND due < ? AND due+duration*60 > ? LIMIT 1",
                           (owner, exclude, due + duration * 60, due)).fetchone()
        if clash:
            raise Clarification(f'That overlaps with {clash["title"]}. Choose another time.')

    def list(self, owner: str, kind: str | None = None, active=True) -> list[dict]:
        query, args = 'SELECT * FROM jobs WHERE owner=?', [owner]
        if kind:
            query += ' AND kind=?'
            args.append(kind)
        if active:
            query += " AND status IN ('active','paused','needs_attention','failed')"
        with self.connection() as db:
            return [dict(r) for r in db.execute(query + ' ORDER BY due LIMIT 1000', args)]

    def find(self, owner: str, kind: str, target: str) -> dict:
        rows = self.list(owner, kind, active=False)
        clock = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', target.lower())
        def clock_matches(row):
            if not clock or not 1 <= int(clock[1]) <= 12:
                return False
            local = datetime.fromtimestamp(row['due'], timezone.utc).astimezone(ZoneInfo(row['timezone']))
            return (local.hour, local.minute) == (int(clock[1]) % 12 + (12 if clock[3] == 'pm' else 0), int(clock[2] or 0))
        matches = [r for r in rows if target and (r['id'] == target or target.casefold() in r['title'].casefold() or clock_matches(r)) and r['status'] != 'cancelled']
        if len(matches) != 1:
            raise Clarification('Please specify one exact title or ID from the list; the target is missing or ambiguous.')
        return matches[0]

    def mutate(self, owner: str, job: dict, operation: str, schedule: Schedule | None = None, calendar_validator=None) -> dict:
        with self.transaction() as db:
            actual = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job['id'], owner)).fetchone()
            if actual is None or actual['version'] != job['version']:
                raise Clarification('This item changed. List it again before making changes.')
            status = {'cancel': 'cancelled', 'complete': 'completed', 'pause': 'paused', 'resume': 'active', 'update': 'active', 'snooze': 'active'}[operation]
            if operation == 'resume' and job['status'] == 'needs_attention':
                raise Clarification('This recurring time needs daylight-saving clarification. Reschedule it with an explicit time before resuming.')
            if operation == 'snooze' and job['recurrence']:
                return self._snooze_occurrence(db, owner, job, schedule)
            due = schedule.at.timestamp() if schedule else job['due']
            recurrence = schedule.recurrence if schedule and operation == 'update' else job['recurrence']
            if job['kind'] == 'event' and status == 'active':
                if calendar_validator:
                    calendar_validator()
                self.check_conflicts(db, owner, due, job['duration'], job['id'])
            db.execute('UPDATE jobs SET status=?,due=?,recurrence=?,version=version+1,updated=? WHERE id=? AND owner=?',
                       (status, due, recurrence, utcnow().timestamp(), job['id'], owner))
            db.execute("UPDATE notifications SET status='cancelled' WHERE job_id=? AND acknowledged IS NULL", (job['id'],))
            # Reset an unsuccessful execution when explicitly resuming or moving an occurrence.
            db.execute("DELETE FROM executions WHERE job_id=? AND status!='succeeded'", (job['id'],))
            self.audit(db, owner, job['id'], operation)
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone())

    def _snooze_occurrence(self, db, owner, job, schedule):
        now = utcnow().timestamp()
        delivered = db.execute("SELECT * FROM notifications WHERE job_id=? AND status='available' ORDER BY occurrence DESC LIMIT 1", (job['id'],)).fetchone()
        # Snooze the last unacknowledged occurrence, otherwise the next scheduled occurrence.
        parent_due = job['due']
        if not delivered:
            parent_due = next_occurrence(datetime.fromtimestamp(job['due'], timezone.utc), job['recurrence'], job['timezone']).timestamp()
        child = uuid4().hex
        db.execute('INSERT INTO jobs(id,owner,kind,title,due,timezone,recurrence,duration,action,create_key,created,updated) VALUES(?,?,?,?,?,?,NULL,60,?,?,?,?)',
                   (child, owner, 'reminder', job['title'] + ' (snoozed)', schedule.at.timestamp(), job['timezone'], '', f"snooze:{job['id']}:{job['version']}", now, now))
        db.execute("UPDATE jobs SET due=?,version=version+1,updated=?,status='active' WHERE id=?", (parent_due, now, job['id']))
        db.execute("UPDATE notifications SET status='cancelled' WHERE job_id=? AND status='available'", (job['id'],))
        self.audit(db, owner, job['id'], 'snooze_occurrence', child)
        result = dict(db.execute('SELECT * FROM jobs WHERE id=?', (child,)).fetchone())
        result['series_id'] = job['id']
        return result

    def notifications(self, owner: str) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM notifications WHERE owner=? AND status='available' ORDER BY created LIMIT 200", (owner,))]

    def acknowledge(self, owner: str, notification_id: str) -> bool:
        with self.transaction() as db:
            updated = db.execute("UPDATE notifications SET status='acknowledged',acknowledged=? WHERE owner=? AND id=? AND status='available'", (utcnow().timestamp(), owner, notification_id)).rowcount
            if updated:
                self.audit(db, owner, None, 'acknowledge', notification_id)
            return bool(updated)

    def history(self, owner: str) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT e.* FROM executions e JOIN jobs j ON j.id=e.job_id WHERE j.owner=? ORDER BY e.started DESC LIMIT 200', (owner,))]
