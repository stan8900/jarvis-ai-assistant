from __future__ import annotations

import httpx

from app.llm.ollama_client import OllamaClient


class BrainError(RuntimeError):
    pass


class MissingBrainKeyError(BrainError):
    pass


async def ask_claude(
    messages: list[dict[str, str]],
    system: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Route to Claude for complex reasoning."""
    if not api_key:
        raise MissingBrainKeyError("ANTHROPIC_API_KEY is not configured.")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise BrainError(
            f"Claude returned HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        raise BrainError(f"Claude request failed: {exc}") from exc

    data = response.json()
    try:
        text = data["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BrainError("Claude returned an unexpected response.") from exc
    return text.strip()


async def ask_openai(
    messages: list[dict[str, str]],
    system: str,
    api_key: str,
    model: str = "gpt-4o-mini",
) -> str:
    """Route to OpenAI for fast writing and analysis."""
    if not api_key:
        raise MissingBrainKeyError("OPENAI_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "max_tokens": 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise BrainError(
            f"OpenAI returned HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        raise BrainError(f"OpenAI request failed: {exc}") from exc

    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BrainError("OpenAI returned an unexpected response.") from exc
    return text.strip()


async def ask_ollama(
    messages: list[dict[str, str]],
    system: str,
    model: str,
    base_url: str,
    timeout_seconds: float,
) -> str:
    """Route to local Ollama for self-hosted conversation."""
    client = OllamaClient(
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    return await client.chat(
        messages=[
            {"role": "system", "content": system},
            *messages,
        ]
    )


BRAIN_ROUTER = {
    "claude": ask_claude,
    "openai": ask_openai,
    "ollama": ask_ollama,
}
