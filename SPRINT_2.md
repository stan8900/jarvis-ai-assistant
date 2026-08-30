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
