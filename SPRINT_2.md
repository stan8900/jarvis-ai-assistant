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
