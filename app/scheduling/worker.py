"""DB-backed leases, bounded retries and transactional inbox dispatch."""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.scheduling.notifications import InAppChannel
from app.scheduling.store import utcnow
from app.scheduling.timeparse import Clarification, next_occurrence

log = logging.getLogger(__name__)


async def daily_briefing(store, job):
    from app.integrations.brief import get_morning_brief
    return await get_morning_brief(owner_id=job['owner'])


async def reminder_summary(store, job):
    reminders = store.list(job['owner'], 'reminder')
    return 'Reminders: ' + ('; '.join(r['title'] for r in reminders[:20]) or 'none')


ACTIONS = {'daily_briefing': daily_briefing, 'reminder_summary': reminder_summary}


class Worker:
    def __init__(self, store, actions=None):
        self.store = store
        self.actions = ACTIONS if actions is None else actions
        self.channel = InAppChannel()

    def claim(self, now):
        with self.store.transaction() as db:
            row = db.execute("""SELECT j.* FROM jobs j LEFT JOIN executions e
                ON e.job_id=j.id AND e.occurrence=j.due
                WHERE j.status='active' AND j.kind!='event' AND j.due<=?
                AND (e.job_id IS NULL OR (e.status IN ('running','retry') AND e.lease_until<=?))
                ORDER BY j.due LIMIT 1""", (now, now)).fetchone()
            if not row:
                return None
            job = dict(row)
            claim = uuid4().hex
            db.execute("""INSERT INTO executions(job_id,occurrence,status,attempts,lease_until,claim,started)
                VALUES(?,?,'running',1,?,?,?) ON CONFLICT(job_id,occurrence)
                DO UPDATE SET status='running',attempts=attempts+1,lease_until=excluded.lease_until,
                claim=excluded.claim,started=excluded.started""", (job['id'], job['due'], now + 90, claim, now))
            job['claim'] = claim
            return job

    async def tick(self, now=None, limit=50):
        timestamp = (now or utcnow()).timestamp()
        for _ in range(limit):
            job = self.claim(timestamp)
            if job is None:
                return
            try:
                if job['kind'] == 'reminder':
                    result = f"Reminder: {job['title']} (due {datetime.fromtimestamp(job['due'], timezone.utc).astimezone(ZoneInfo(job['timezone'])).isoformat()})"
                else:
                    action = self.actions.get(job['action'])
                    if action is None:
                        raise ValueError('Unapproved automation action')
                    result = await asyncio.wait_for(action(self.store, job), timeout=30)
                self.finish(job, timestamp, result)
            except Exception:
                # Do not store provider errors or private CRM content in logs.
                self.fail(job, timestamp, 'Execution failed; check the configured local action/provider.')

    def finish(self, job, now, result):
        with self.store.transaction() as db:
            current = db.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone()
            run = db.execute('SELECT * FROM executions WHERE job_id=? AND occurrence=?', (job['id'], job['due'])).fetchone()
            if not current or not run or current['version'] != job['version'] or current['status'] != 'active' or run['claim'] != job['claim']:
                return
            self.channel.deliver(db, job, result, now)
            db.execute("UPDATE executions SET status='succeeded',finished=?,result=?,lease_until=0 WHERE job_id=? AND occurrence=?", (now, result, job['id'], job['due']))
            status, due = 'completed', job['due']
            if job['recurrence']:
                try:
                    upcoming = next_occurrence(datetime.fromtimestamp(job['due'], timezone.utc), job['recurrence'], job['timezone'])
                    skipped = 0
                    # Reminders catch up every occurrence. Read-only automations coalesce missed runs.
                    if job['kind'] == 'automation':
                        while upcoming.timestamp() <= now and skipped < 100000:
                            upcoming = next_occurrence(upcoming, job['recurrence'], job['timezone'])
                            skipped += 1
                        if skipped:
                            self.store.audit(db, job['owner'], job['id'], 'coalesced_missed_runs', str(skipped))
                    status, due = 'active', upcoming.timestamp()
                except Clarification:
                    status = 'needs_attention'
                    self.store.audit(db, job['owner'], job['id'], 'dst_clarification_required')
                    db.execute("UPDATE notifications SET content=content || ? WHERE job_id=? AND occurrence=?",
                               (' Next recurrence needs daylight-saving clarification; please reschedule the series.', job['id'], job['due']))
            db.execute('UPDATE jobs SET status=?,due=?,updated=? WHERE id=?', (status, due, now, job['id']))
            self.store.audit(db, job['owner'], job['id'], 'inbox_stored')

    def fail(self, job, now, error):
        with self.store.transaction() as db:
            row = db.execute('SELECT e.* FROM executions e JOIN jobs j ON j.id=e.job_id WHERE e.job_id=? AND e.occurrence=? AND e.claim=? AND j.version=? AND j.status=\'active\'',
                             (job['id'], job['due'], job['claim'], job['version'])).fetchone()
            if not row:
                return
            exhausted = row['attempts'] >= 3
            db.execute('UPDATE executions SET status=?,error=?,lease_until=?,finished=? WHERE job_id=? AND occurrence=?',
                       ('failed' if exhausted else 'retry', error, now + 30 * 2 ** (row['attempts'] - 1), now, job['id'], job['due']))
            if exhausted:
                db.execute("UPDATE jobs SET status='failed' WHERE id=?", (job['id'],))
                self.channel.deliver(db, job, f"Scheduled item failed after three attempts: {job['title']}. Resume it to retry.", now)
            self.store.audit(db, job['owner'], job['id'], 'failed' if exhausted else 'retry')

    async def run(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.error('Scheduling worker tick failed; pending work remains in the database.')
            await asyncio.sleep(5)
