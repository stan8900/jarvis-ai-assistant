# Scheduling, reminders and local automations

## Status

Implemented: persistent reminders, recurring schedules, owner-scoped authenticated APIs,
local calendar creation and conflict checks, confirmations, a durable notification inbox,
allowlisted automations, execution history, restart recovery, and voice-client inbox polling.

Bold REST integration is now connected through the documented `/rest/*` routes. The
adapter uses the configured bearer token, HTTPS only, bounded retries for network/5xx/
429 failures, and no retries for authentication failures. All external mutations require
the existing Jarvis confirmation flow. Bold tasks remain separate from Jarvis reminders:
Bold's `dueAt` does not itself deliver a notification.

## Architecture and changed files

The existing flow remains FastAPI → ToolRouter → tools / conversation orchestrator.
Redis conversation context and Postgres long-term memory retain their existing behavior.
Those memory implementations can fall back to volatile storage, so scheduled work instead
uses a separate durable SQLite database with explicit transactions and no memory fallback.
No new third-party Python dependency is needed.

| File | Purpose |
| --- | --- |
| `app/scheduling/models.py`, `parser.py` | Validated commands; deterministic intent detection independent of execution |
| `app/scheduling/timeparse.py` | IANA timezone validation, date parsing, DST checks and recurrence |
| `app/scheduling/store.py`, `migrations/001_initial.sql` | Jobs, executions, inbox, confirmations, audit log, reserved CRM mappings |
| `app/scheduling/service.py` | Owner-scoped command lifecycle, preview and confirmation |
| `app/scheduling/calendar.py` | Local event operations plus read-only existing JSON calendar |
| `app/scheduling/worker.py`, `notifications.py` | Durable worker leases, retries, transactional in-app delivery |
| `app/scheduling/security.py` | Scheduling bearer credential, owner binding and rate limit |
| `app/scheduling/client.py` | Shared authenticated client helpers and durable-inbox polling |
| `app/scheduling/bold.py` | Authenticated Bold REST adapter and disabled fallback |
| `app/api/routes_schedule.py` | Structured and natural-language commands, lists, inbox and history |
| `app/api/routes_chat.py` | Scheduling in text/audio requests without requiring TTS/LLM; bounded audio uploads |
| `app/main.py` | Scheduler startup and cancellation on shutdown |
| `app/brain/tool_router.py`, `orchestrator.py` | Safe scheduling interception; authenticated daily-brief summary context |
| `app/integrations/calendar.py`, `brief.py` | Strict calendar reads for conflict checking; optional real scheduling counts; remove fabricated fallback priorities |
| `app/cli/voice_loop.py` | Bearer and idempotency headers, inbox polling, credential transport validation |
| `tests/test_scheduling.py` | Unit, API, provider-boundary and regression tests |
| `.env.scheduling.example`, `data/.gitignore` | Configuration template and private-database exclusion |

### Data and lifecycle

Migration 001 initializes a new `data/scheduling.sqlite3` on first service use. It does not
alter `jarvis.db` or Postgres. `schema_version` records the migration. Jobs store owner,
kind, title, UTC occurrence, original IANA timezone, recurrence, status, duration, action,
version, creation key and timestamps. Other tables hold executions, notification
acknowledgements, expiring confirmations, audit records and the future CRM mapping contract.
Back up the database using SQLite's backup API or with the application stopped.

A five-second worker loop claims due reminders/automations under `BEGIN IMMEDIATE` with
a 90-second lease. Actions have a 30-second timeout. Inbox insertion, execution completion
and next occurrence advancement commit together. A unique `(job_id, occurrence)` key
prevents duplicate durable notifications, including after a crash. Worker instances on the
same host may share a local SQLite file. Do not share it over a network filesystem or
across independently replicated hosts; that deployment needs a central database worker.

Overdue reminders catch up every occurrence, bounded to 50 per tick. They remain stored
until processed. Read-only automations execute once after downtime and coalesce missed
occurrences; the number is audited. Failures retry after 30 and 60 seconds, then enter
`failed` with an inbox report. Resume explicitly to retry. DST recurrence ambiguity enters
`needs_attention` with an audit record, rather than silently changing the time. Reschedule
that series with an explicit time. Calendar events are projected from their stored start
and recurrence and do not run executable jobs.

## Configuration and running

The local ignored `.env` has been prepared with a generated scheduling credential and
London timezone without replacing existing AI/voice settings. Restart the API and voice
client to load it. For another installation, merge `.env.scheduling.example` into its existing `.env`. Generate a random secret with the command in the template. Never commit `.env`
or share the scheduling token. The existing API loader reads `.env` at startup.

| Variable | Default / requirement |
| --- | --- |
| `JARVIS_SCHEDULER_TOKEN` | Required for API access; at least 32 characters |
| `JARVIS_SCHEDULER_OWNER` | `sultan`; this installation is single-owner |
| `JARVIS_TIMEZONE` | `Europe/London`; valid IANA name required |
| `JARVIS_SCHEDULER_DB` | Absolute project path to `data/scheduling.sqlite3` |
| `JARVIS_SCHEDULER_ENABLED` | `true`; set `false` to stop executing jobs, while retaining storage |
| `BOLD_API_BASE_URL` | `https://bold-production.up.railway.app` |
| `BOLD_API_TOKEN` | Required for Bold commands; keep secret and rotate before expiry |
| `BOLD_REQUEST_TIMEOUT_SECONDS` | `15` |

Start the existing API:

```sh
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep this process and its database available. A sleeping/offline machine cannot deliver
reminders at the intended time. Pending work is recovered on restart. Voice and model
configuration remain independent; the scheduling text endpoint works without a model,
Redis, Postgres or a TTS voice. Existing TTS warm-up may still take time at API startup;
set `JARVIS_XTTS_WARM=false` if you want to skip XTTS warming.

## Commands

- `Remind me tomorrow at 9 AM to call David`
- `Remind me in 30 minutes to check the server`
- `Remind me every Monday at 9 AM to review my projects`
- `Remind me every weekday at 18:00 to review unfinished work`
- `Remind me every month on 1 at 09:00 to review expenses`
- `What reminders do I have today?`
- `List my reminders`
- `Move my report reminder to tomorrow at 10 AM`
- `Move my 6 PM reminder to tomorrow` (preserves its local clock time)
- `Snooze my report reminder for 30 minutes`
- `Complete my report reminder`
- `Cancel my reminder about the report`
- `Schedule a meeting with David tomorrow at 2 PM`
- `Block 120 minutes for programming tomorrow at 10 AM`
- `Cancel my meeting with Alex`
- `Move my meeting with David to Friday at 2 PM`
- `What is my schedule next week?`
- `Find a free 30-minute slot tomorrow`
- `Run my daily briefing every morning at 8 AM`
- `Run my reminder summary every weekday at 17:00`
- `Run my reminder summary every 30 minutes`
- `Show all active automations`
- `Pause my daily briefing automation`
- `Resume my daily briefing automation`
- `Delete my daily briefing automation`

The parser deliberately requests clarification for “tomorrow morning”, a time with no
AM/PM or 24-hour notation, a missing deadline, or multiple matching titles. ISO timestamps
with explicit UTC offsets disambiguate DST folds. Explicit past times are rejected.
An unqualified `at 6 PM` means the next occurrence of 18:00. Day/week relative intervals
are elapsed durations; daily/weekly/monthly recurrence preserves the local wall time.
For an unrecognized expression, send a new command including the clarified details; there
is no implicit multi-turn date inference.

Cancellation, completion, snoozing, rescheduling, pause/resume and event creation produce
a preview. Send `confirm <confirmation_id>` in the same owner/session within ten minutes.
You can also say `confirm` when exactly one change is pending in that session. The confirmation holds an absolute resolved time and target version; stale or expired
previews are rejected. Structured API callers can instead submit `confirmed: true` after
showing the full operation to the user. Reminder creation itself needs no confirmation.
Rescheduling a series without recurrence converts it to a one-time job; include `every …`
to keep recurrence. Completing/cancelling a recurring reminder applies to the whole series.
Snoozing a series creates a one-time deferred occurrence while preserving the series.

The two approved automation actions are `daily_briefing` and `reminder_summary`. No shell
commands, messages to others, CRM writes, or arbitrary tools are runnable by the worker.
Project/task summaries need a verified data provider before they can become actions.

## API contract

All `/api/schedule/*` routes require `Authorization: Bearer <JARVIS_SCHEDULER_TOKEN>`.
The server maps that token to the configured owner. A request `user_id` cannot grant
scheduling ownership. Authentication is also required for scheduling commands submitted
to `/api/chat/text` or `/api/chat/audio`. General conversation retains its existing behavior.
Daily briefings with this credential optionally include real local scheduling counts.

New creations require a unique `Idempotency-Key` header (or the structured command's
`idempotency_key`). Reuse it for retries of the exact same command; use a new key for a
new item. Relative-date retries return the original record rather than reparsing its time.
A reused key with a different payload returns clarification without another write.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| POST | `/api/schedule/text` | `{ "message": "...", "session_id": "default" }` |
| POST | `/api/schedule/commands` | Validated structured `Command`; session is `api` |
| GET | `/api/schedule/reminders` | Owner's non-cancelled pending/paused/failed reminders |
| GET | `/api/schedule/automations` | Owner's pending/paused/failed automations |
| GET | `/api/schedule/notifications` | Durable inbox, channel and device-delivery status |
| POST | `/api/schedule/notifications/{id}/ack` | Explicit acknowledgement |
| GET | `/api/schedule/history` | Owner's last 200 execution records |

A structured command example:

```json
{
  "intent": "CREATE_REMINDER",
  "title": "Call David",
  "when": "tomorrow at 9 AM",
  "timezone": "Europe/London",
  "idempotency_key": "a-unique-client-request-id"
}
```

Responses distinguish `created`, `existing`, `updated`, `ok`, `confirmation_required`,
`clarification_required` and `unavailable`. Items include their identifiers and exact UTC
schedule; human-readable responses include the IANA timezone and local UTC offset.
Authentication errors use 401; absent token configuration uses 503; invalid payloads use
422; missing creation keys use 428. Scheduling is limited to 120 requests/minute per
process/owner (429 with Retry-After). A distributed deployment needs gateway rate limits.

For a local API request without printing the token:

```sh
.venv/bin/python - <<'PY'
import os, uuid, httpx
from app.core.config import get_settings  # loads existing .env
response = httpx.post(
    'http://127.0.0.1:8000/api/schedule/text',
    headers={'Authorization': 'Bearer ' + os.environ['JARVIS_SCHEDULER_TOKEN'],
             'Idempotency-Key': uuid.uuid4().hex},
    json={'message': 'Remind me in 30 minutes to check the server'},
)
print(response.json())
PY
```

## Notifications and voice

The initial notification channel is the in-app inbox. A successful execution means the
notification is durably **stored**, not that a device displayed or spoke it. Reading the
inbox does not acknowledge it. An authenticated client acknowledges only after display.
There is no offline push, desktop popup, email, invitation or mobile delivery integration.

The existing voice CLI attaches its scheduling credential and a unique request key, and
polls/displays inbox notifications between recording cycles. It loads the same local `.env` as the API; exported environment variables take precedence. Credentials are sent only to
HTTPS or loopback addresses. It does not automatically speak pending notifications.
Text/audio scheduling responses remain available without TTS. Only the active voice CLI
prints due notifications; other clients must poll `/notifications` and display them.

## Calendar behavior and limits

The existing `data/calendar/events.json` remains a read-only calendar source. New local
events live in SQLite. Listings and free-slot checks combine both. Local edits require
confirmation and are transactional; legacy JSON events require editing their original
source and cannot be modified through the new commands. Unknown or ambiguous targets
request clarification instead of changing the first record found.

Events default to 60 minutes and previews state the duration. Structured requests can
specify `duration_minutes` from 1 to 1440. Free-time search uses 09:00–17:00 in the configured
timezone. Recurring-event conflict expansion covers the next 366 days from the proposed
start, not the indefinite future; calendar queries expand actual occurrences. Concurrent
local writes revalidate conflicts under the write transaction. No external calendar
provider is connected, no invitations are sent, and local availability does not establish
availability in a remote account.

## Bold setup and synchronization

Create a restricted Bold `JARVIS` role and API token as described in the supplied Bold
documentation. Grant only Notes/Tasks read and update/create permissions, and read access
to People, Companies, and Calendar events. Do not put tokens in chat. `BOLD_API_TOKEN` is
loaded from `.env` and is never logged.

The adapter supports listing/retrieving/creating/updating Notes and Tasks, plus listing the
other documented object types. It sends `Idempotency-Key` on creates, maps task completion
to the documented `DONE` status, and keeps remote version metadata for conditional updates.
The reserved `crm_links` table records local and remote IDs/types, title/description, due
time, timezone, completion/recurrence, sync timestamp/status, remote version and source of
truth. The policy is remote-authoritative CRM content and local-authoritative notification
schedule. If Bold lacks reminder metadata, the notification remains local and is labeled
separately from the remote task. Calendar events are read-only because Bold documents them
as synchronized system records.

## Validation and manual acceptance

Run:

```sh
JARVIS_SCHEDULER_ENABLED=false JARVIS_XTTS_WARM=false \
  .venv/bin/python -m unittest discover -s tests -v
```

Validation result: **70 tests passed**, including real application worker startup/shutdown
against a temporary database and mocked text/audio clients. Python compilation was also
checked for the changed modules.

Tests use temporary databases and mocked/read-only providers; no live CRM mutations,
invitations or production recurring automations run. Coverage includes deterministic
intent/date handling, DST gaps/folds, recurrence, cancellation and snoozing, transaction
leases, concurrent workers, crash/restart recovery, durable notification deduplication,
bounded retries and failure reports, confirmations/ownership, API auth/rate limits,
calendar conflicts, disabled Bold behavior, untrusted contents remaining inert, and
existing command regression. Live Bold authentication/retry/sync tests are inapplicable
until the actual API exists; no mock endpoint is presented as a verified integration.

Manual checks (create only disposable local test items):

1. Configure the token and London timezone, start the API, and submit a reminder with a new key.
2. Repeat that HTTP request with the same key and verify the same ID is returned.
3. List reminders; preview/reschedule one and confirm in the same session.
4. Create a short reminder, stop/restart the API across its due time, then verify one inbox entry.
5. Read without acknowledging, restart, and verify the entry persists. Acknowledge and verify removal.
6. Create a recurring reminder; snooze one occurrence and verify the next series time remains unchanged.
7. Preview a calendar event; confirm it, then request an overlapping event and check the conflict response.
8. Request a daily briefing automation at an explicit time, then pause/resume/delete it with confirmation.
9. Verify no-token scheduling requests fail and general time/weather/editor commands still work.
10. Verify a Bold list request reads tasks, then create a disposable task and confirm the
    mutation before checking it in Bold. Complete it only after confirming the update.
11. Verify an expired/revoked token returns an authentication error without retries.
