from __future__ import annotations

import logging
import re

import httpx


logger = logging.getLogger(__name__)

DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
MAX_SUMMARY_CHARS = 220


async def web_search(query: str) -> str:
    clean_query = query.strip()
    if not clean_query:
        return "I need a subject to search for, sir."

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            summary = ""
            for candidate_query in _candidate_queries(clean_query):
                data = await _fetch_instant_answer(client, candidate_query)
                summary = _extract_summary(data)
                if summary:
                    break
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("Web search failed: %s", exc)
        return "I was unable to complete the search, sir."

    if not summary:
        return "I wasn't able to find a clear answer on that, sir."

    return _format_for_speech(summary)


async def _fetch_instant_answer(client: httpx.AsyncClient, query: str) -> dict:
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    }
    response = await client.get(DUCKDUCKGO_URL, params=params)
    response.raise_for_status()
    return response.json()


def _candidate_queries(query: str) -> list[str]:
    queries = [query]
    if "fastapi" in query.lower():
        queries.append("FastAPI web framework")
    queries.append(f"{query} web framework")
    return list(dict.fromkeys(queries))


def _extract_summary(data: dict) -> str:
    abstract = data.get("AbstractText")
    if abstract:
        return str(abstract)

    for topic in data.get("RelatedTopics") or []:
        text = _topic_text(topic)
        if text:
            return text

    return ""


def _topic_text(topic: dict) -> str:
    if not isinstance(topic, dict):
        return ""
    if topic.get("Text"):
        return str(topic["Text"])

    for nested in topic.get("Topics") or []:
        text = _topic_text(nested)
        if text:
            return text
    return ""


def _format_for_speech(text: str) -> str:
    cleaned = _strip_urls(text)
    cleaned = re.sub(r"[_*`~#<>\[\]{}|]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _first_sentence(cleaned)
    if len(cleaned) > MAX_SUMMARY_CHARS:
        cleaned = cleaned[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0].strip(" ,;:-")

    if not cleaned:
        return "I wasn't able to find a clear answer on that, sir."
    if not cleaned.lower().endswith(("sir", "sir.")):
        cleaned = f"{cleaned.rstrip('.').rstrip()}, sir."
    return cleaned


def _strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+|www\.\S+", "", text)


def _first_sentence(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected = next((sentence for sentence in sentences if sentence), "")
    return selected or text
