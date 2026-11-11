from __future__ import annotations


def select_brain(
    user_message: str,
    tool_used: str | None = None,
    default_brain: str = "ollama",
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

    return "ollama"
