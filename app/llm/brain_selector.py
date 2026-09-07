from __future__ import annotations


def select_brain(
    user_message: str,
    tool_used: str | None = None,
    default_brain: str = "claude",
) -> str:
    """
    Decide which brain should handle normal conversation.

    Tool responses are already handled before this function is needed, but the
    tool branch remains explicit so callers can log a consistent fallback.
    """
    if tool_used:
        return "ollama"

    message_lower = user_message.lower().strip()
    for wake_word in ("jarvis, ", "jarvis "):
        if message_lower.startswith(wake_word):
            message_lower = message_lower[len(wake_word) :].strip()
            break

    openai_triggers = [
        "write me",
        "draft",
        "creative",
        "story",
        "email",
    ]
    if any(trigger in message_lower for trigger in openai_triggers):
        return "openai"

    simple_factual_starts = (
        "what is ",
        "who is ",
        "when is ",
        "where is ",
        "define ",
        "how many ",
        "how much ",
    )
    if (
        message_lower.startswith(simple_factual_starts)
        and len(message_lower.split()) <= 14
    ):
        return "ollama"

    complex_triggers = [
        "help me",
        "advice",
        "should i",
        "what do you think",
        "explain",
        "how do i",
        "interview",
        "career",
        "write",
        "analyse",
        "analyze",
        "compare",
        "plan",
        "strategy",
        "jarvis think",
    ]
    if any(trigger in message_lower for trigger in complex_triggers):
        return "claude"

    if default_brain in {"claude", "openai", "ollama"}:
        return default_brain
    return "claude"
