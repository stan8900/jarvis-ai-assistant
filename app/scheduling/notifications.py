"""Channel contract: the durable inbox confirms storage, not device delivery."""
from typing import Protocol
from uuid import uuid4


class NotificationChannel(Protocol):
    name: str
    def deliver(self, db, job: dict, content: str, now: float) -> None: ...


class InAppChannel:
    name = 'in_app'

    def deliver(self, db, job: dict, content: str, now: float) -> None:
        db.execute('INSERT OR IGNORE INTO notifications(id,owner,job_id,occurrence,content,created) VALUES(?,?,?,?,?,?)',
                   (uuid4().hex, job['owner'], job['id'], job['due'], content, now))
