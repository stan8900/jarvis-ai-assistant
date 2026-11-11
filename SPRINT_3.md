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

## Task 2 - Multi-LLM Brain

Status: Done

JARVIS now routes normal conversation across two active brain tiers:

- `openai` for complex reasoning, interviews, career advice, strategy, planning,
  drafting, writing, email, and creative work.
- `ollama` for local fallback and self-hosted operation when API keys are unavailable.

Tool responses still bypass external providers and return immediately as
`tool:<name>`, preserving the low-latency path for time, date, weather, search,
brief, memory, calendar, and IDE commands.

Environment:

```text
OPENAI_API_KEY=...
JARVIS_DEFAULT_BRAIN=openai
JARVIS_OPENAI_MODEL=gpt-4o-mini
```

Acceptance prompts:

```text
Jarvis what time is it
Jarvis help me prepare for my Palantir interview
Jarvis draft an email to a recruiter
Jarvis jarvis think about my career strategy
```
