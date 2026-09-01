# Sprint 2 - Tool Router Foundation

Status: In progress
Start date: 30 August 2026

## Task 1 - Tool Router Foundation

Status: Done

JARVIS now checks deterministic tool intents before calling Ollama. If a tool
matches, the orchestrator returns the tool result directly and sends it to TTS.
If no tool matches, the normal LLM conversation path is unchanged.

Implemented tools:

```text
Time           "what time is it"       -> "It's HH:MM, sir."
Date           "what's today's date"   -> "Sunday the 30th of August, sir."
Weather        "what's the weather"    -> "Weather service not yet connected, sir."
Morning brief  "morning brief"         -> "Morning brief not yet configured, sir."
Morning brief  "what's my plan"        -> "Morning brief not yet configured, sir."
```

Acceptance checks:

```text
Jarvis what time is it       -> tool:time
Jarvis what's the weather    -> tool:weather
Jarvis what's today's date   -> tool:date
Jarvis morning brief         -> tool:morning_brief
Normal conversation          -> LLM path
```

## Task 2 - Real Weather Integration

Status: Done

The weather tool now calls Open-Meteo directly. It uses London as the default
location, requires no API key, and converts WMO weather codes into plain
English before JARVIS speaks the result.

Implemented triggers:

```text
"weather"
"what's it like outside"
"should I bring a jacket"
"temperature"
```

Example response:

```text
overcast, 19 degrees, sir.
```

## Task 3 - Web Search Integration

Status: Done

JARVIS now routes search-style questions to DuckDuckGo Instant Answer before
Ollama. Responses are cleaned for speech, stripped of URLs and markup, and kept
to one concise sentence for XTTS.

Implemented triggers:

```text
"search for"
"look up"
"find out"
"what is"
"who is"
"tell me about"
```

Example responses:

```text
Elon Reeve Musk is a businessman and former public official who is the CEO and
largest shareholder of Tesla and SpaceX, sir.

FastAPI is a web framework for building HTTP-based service APIs in Python 3.8+,
sir.
```

## Task 4 - Morning Brief

Status: Done

JARVIS now produces a single spoken morning brief with a time-aware greeting,
today's date, live London weather, and configurable priorities from
`data/brief_config.json`.

Implemented triggers:

```text
"good morning"
"good afternoon"
"good evening"
"morning brief"
"what's my plan"
"what should I focus on"
```

Editable config:

```json
{
  "daily_tasks": [
    "5 job applications",
    "Rasylon emails",
    "JARVIS Sprint 2",
    "20 pages reading",
    "Linear algebra"
  ],
  "wake_time": "05:30",
  "location": "London"
}
```

## Task 5 - Calendar Integration

Status: Done

JARVIS now reads a local calendar from `data/calendar/events.json`, routes
calendar questions before Ollama, and includes today's schedule in the morning
brief. This keeps Sprint 2 self-hosted and avoids OAuth/API setup until it is
needed.

Implemented triggers:

```text
"calendar"
"schedule today"
"what meetings do I have"
"what's on my schedule"
"what's on my calendar"
```

Editable calendar:

```json
{
  "events": [
    {
      "title": "JARVIS Sprint 2",
      "date": "2026-08-31",
      "start_time": "10:00",
      "end_time": "12:00"
    }
  ]
}
```

## Task 6 - Long-Term Memory

Status: Done

JARVIS now has real PostgreSQL-backed long-term memory. It creates `facts` and
`interactions` tables on startup, stores remembered facts with upsert semantics,
recalls saved facts after restart, and logs every user and assistant turn. If
PostgreSQL is unavailable, it falls back to in-memory storage so the assistant
keeps running.

Configuration:

```text
JARVIS_POSTGRES_URL=postgresql://jarvis:jarvis@localhost:5432/jarvis
```

Initial schema:

```text
facts(id, key, value, created_at, updated_at)
interactions(id, session_id, role, content, tool_used, created_at)
```

Implemented triggers:

```text
"remember that"
"don't forget"
"note that"
"what do you know about me"
"what do you remember about me"
```

## Task 7 - IDE Control

Status: Done

JARVIS now routes IDE commands to local process controls for VS Code,
Antigravity IDE, and the FastAPI server. File opening searches the project tree
and skips virtualenv, cache, and Git directories. IDE actions skip TTS so they
return immediately.

Implemented triggers:

```text
"open VS Code"
"open vscode"
"open Antigravity"
"open Antigravity IDE"
"open file"
"open the"
"start the server"
"run the server"
```

Examples:

```text
Jarvis open VS Code        -> Opening VS Code, sir.
Jarvis open Antigravity    -> Opening Antigravity IDE, sir.
Jarvis open the tool router -> Opening tool_router.py, sir.
Jarvis start the server    -> Starting the server, sir.
```
