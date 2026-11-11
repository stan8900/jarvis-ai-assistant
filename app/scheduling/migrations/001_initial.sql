CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
 title TEXT NOT NULL, due REAL NOT NULL, timezone TEXT NOT NULL,
 recurrence TEXT, duration INTEGER NOT NULL DEFAULT 60,
 action TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
 version INTEGER NOT NULL DEFAULT 1, create_key TEXT NOT NULL,
 created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(owner, create_key)
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(status,due);
CREATE TABLE IF NOT EXISTS executions (
 job_id TEXT NOT NULL REFERENCES jobs(id), occurrence REAL NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_until REAL NOT NULL DEFAULT 0, claim TEXT, error TEXT,
 started REAL, finished REAL, result TEXT,
 PRIMARY KEY(job_id, occurrence)
);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, job_id TEXT NOT NULL,
 occurrence REAL NOT NULL, content TEXT NOT NULL, created REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'available', acknowledged REAL,
 UNIQUE(job_id, occurrence)
);
CREATE TABLE IF NOT EXISTS confirmations (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, session TEXT NOT NULL,
 payload TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, owner TEXT NOT NULL, job_id TEXT,
 operation TEXT NOT NULL, created REAL NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
-- Reserved mapping contract. No Bold transport is enabled without verified API support.
CREATE TABLE IF NOT EXISTS crm_links (
 owner TEXT NOT NULL, local_id TEXT NOT NULL, provider TEXT NOT NULL,
 record_id TEXT NOT NULL, record_type TEXT NOT NULL, title TEXT NOT NULL,
 description TEXT, due REAL, timezone TEXT, completion_status TEXT,
 recurrence TEXT, last_sync REAL, sync_status TEXT NOT NULL DEFAULT 'unverified',
 remote_version TEXT, source_of_truth TEXT NOT NULL DEFAULT 'remote',
 UNIQUE(owner,local_id,provider), UNIQUE(owner,provider,record_type,record_id)
);
