# Sprint 3 - Make JARVIS Genuinely Intelligent

Status: In progress
Start date: 1 September 2026

## Task 1 - Upgrade To llama3.1:8b

Status: Done

JARVIS now defaults to `llama3.1:8b` for stronger local reasoning and more
natural conversation. The request timeout is now 120 seconds to allow slower
CPU responses from the larger local model.

Runtime override:

```text
JARVIS_OLLAMA_MODEL=llama3.1:8b
JARVIS_REQUEST_TIMEOUT_SECONDS=120
```

Acceptance prompt:

```text
Jarvis, help me plan today around my calendar and job applications.
```
