#!/usr/bin/env python3
"""Lightweight query analysis for Butler's info-seeking flows."""

from __future__ import annotations

import re

URL_PATTERN = re.compile(
    r"(https?://[^\s]+|www\.[^\s]+|\b[a-z0-9.-]+\.(?:com|org|net|io|ai|dev|app|co|in)(?:/[^\s]*)?)",
    re.IGNORECASE,
)

NEWS_PATTERNS = (
    "latest news",
    "recent news",
    "breaking news",
    "news about",
    "news on",
    "news in",
    "what happened in",
    "what's happening in",
    "whats happening in",
    "today",
    "last 24 hours",
)

SEARCH_PATTERNS = (
    "what is",
    "what's",
    "whats",
    "who is",
    "when did",
    "where is",
    "look up",
    "search",
    "find",
    "latest",
    "new",
    "recent",
    "current",
    "price",
    "stock",
    "weather",
    "update",
)

FETCH_PATTERNS = (
    "read this",
    "this article",
    "this page",
    "from this url",
    "from this link",
    "analyze this link",
    "summarize this page",
    "read this website",
)

INTERNAL_PATTERNS = (
    "explain",
    "how to",
    "how does",
    "define",
    "concept",
    "theory",
    "python",
    "javascript",
    "code",
    "math",
    "history",
    "science",
)


def _normalize(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _normalize_url(url: str) -> str:
    cleaned = str(url or "").strip().rstrip(".,);!?]}")
    if not cleaned:
        return ""
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    if cleaned.startswith("www."):
        return f"https://{cleaned}"
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"
    return cleaned


def _extract_url(text: str) -> str:
    match = URL_PATTERN.search(str(text or ""))
    if not match:
        return ""
    return _normalize_url(match.group(1))


def analyze_query(text: str, conversation: str = "") -> dict:
    cleaned = _normalize(text)
    lowered = cleaned.lower()
    extracted_url = _extract_url(cleaned)
    has_url = bool(extracted_url)
    conversation_present = bool(_normalize(conversation))

    if has_url:
        return {
            "action": "fetch",
            "confidence": 0.95,
            "reason": "Query includes a URL or domain.",
            "query": cleaned,
            "url": extracted_url,
            "time_sensitive": False,
            "conversation_present": conversation_present,
        }

    if any(pattern in lowered for pattern in FETCH_PATTERNS):
        return {
            "action": "fetch",
            "confidence": 0.88,
            "reason": "User asked Butler to read or analyze a specific page.",
            "query": cleaned,
            "url": extracted_url,
            "time_sensitive": True,
            "conversation_present": conversation_present,
        }

    if any(pattern in lowered for pattern in NEWS_PATTERNS):
        return {
            "action": "news",
            "confidence": 0.84,
            "reason": "Query is current-event oriented.",
            "query": cleaned,
            "time_sensitive": True,
            "conversation_present": conversation_present,
        }

    if any(pattern in lowered for pattern in SEARCH_PATTERNS):
        return {
            "action": "search",
            "confidence": 0.76,
            "reason": "Query likely needs live lookup or web verification.",
            "query": cleaned,
            "time_sensitive": any(token in lowered for token in ("latest", "recent", "current", "today", "new")),
            "conversation_present": conversation_present,
        }

    if any(pattern in lowered for pattern in INTERNAL_PATTERNS):
        return {
            "action": "internal",
            "confidence": 0.72,
            "reason": "Query is conceptual and can be answered from Butler's model context.",
            "query": cleaned,
            "time_sensitive": False,
            "conversation_present": conversation_present,
        }

    return {
        "action": "internal",
        "confidence": 0.58,
        "reason": "Defaulted to internal reasoning because the request is not clearly live-data dependent.",
        "query": cleaned,
        "time_sensitive": False,
        "conversation_present": conversation_present,
    }
