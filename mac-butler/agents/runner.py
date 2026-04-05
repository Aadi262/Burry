#!/usr/bin/env python3
"""
agents/runner.py
Specialist agent runner for Butler's delegated tasks.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.parse

import numpy as np
import requests

from butler_config import AGENT_MODEL_CHAINS, AGENT_MODELS, EXA_API_KEY, OLLAMA_MODEL
from brain.ollama_client import (
    _get_available_models,
    _check_memory,
    _get_request_target_for_model,
    _unload_model,
    pick_agent_model,
)
from mcp import MCPError, call_server_tool, list_server_tools, normalize_tool_result
from butler_secrets.loader import get_vps_secret
from runtime import note_agent_result

ROUTED_MODELS = {
    agent_type: (chain[0] if chain else AGENT_MODELS.get(agent_type, OLLAMA_MODEL))
    for agent_type, chain in AGENT_MODEL_CHAINS.items()
}
ROUTED_MODELS.update(AGENT_MODELS)
ROUTED_MODELS["default"] = OLLAMA_MODEL

_installed_models: set[str] = set()
_LAST_FETCH_DATA: dict = {}
_SEARXNG_AVAILABLE: bool | None = None
REDDIT_HEADERS = {"User-Agent": "Butler/1.0"}
GITHUB_HEADERS = {"User-Agent": "Butler/1.0"}


def _get_installed_models() -> set[str]:
    global _installed_models
    if _installed_models:
        return _installed_models
    try:
        _installed_models = _get_available_models()
        return _installed_models
    except Exception:
        return set()


def _pick_model(agent_type: str) -> str:
    model = pick_agent_model(agent_type)
    installed = _get_installed_models()
    if installed and model not in installed and model.split(":")[0] not in installed:
        preferred = ROUTED_MODELS.get(agent_type, ROUTED_MODELS["default"])
        print(f"[Agent] {preferred} not installed, using {model}")
    return model


def _prepare_model_request(model: str) -> None:
    _check_memory()
    for candidate in {name for name in ROUTED_MODELS.values() if name and name != model}:
        _unload_model(candidate)


def _call_model(prompt: str, model: str, max_tokens: int = 400, timeout: int = 90) -> str:
    _prepare_model_request(model)
    url, headers, _backend = _get_request_target_for_model(model)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "2m",
        "options": {
            "temperature": 0.3,
            "num_predict": max_tokens,
            "num_ctx": 1024,
        },
    }
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json().get("response", "").strip()


def _limit_words(text: str, limit: int = 150) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) <= limit:
        return cleaned
    return " ".join(words[:limit]).rstrip(",;:-") + "..."


def _truncate_items(items: list[dict], limit: int = 5) -> list[dict]:
    return [dict(item) for item in items[:limit] if isinstance(item, dict)]


def _fallback_items_summary(items: list[dict], empty_message: str) -> str:
    if not items:
        return empty_message
    lines = []
    for item in items[:3]:
        title = str(item.get("title", "")).strip() or "Untitled"
        score = item.get("score")
        if score is None:
            lines.append(f"- {title}")
        else:
            lines.append(f"- {title} ({score})")
    return _limit_words("\n".join(lines), limit=150)


def _fallback_text_summary(material: str, empty_message: str) -> str:
    lines = []
    for raw_line in str(material or "").splitlines():
        cleaned = " ".join(raw_line.split()).strip(" -")
        if not cleaned:
            continue
        lines.append(f"- {cleaned[:120]}")
        if len(lines) >= 3:
            break
    if not lines:
        return empty_message
    return _limit_words("\n".join(lines), limit=150)


def _safe_model_summary(
    prompt: str,
    model: str,
    items: list[dict],
    *,
    empty_message: str,
    max_tokens: int = 180,
    timeout: int = 12,
) -> str:
    if not items:
        return empty_message
    try:
        summary = _call_model(prompt, model, max_tokens=max_tokens, timeout=timeout)
        cleaned = _limit_words(summary, limit=150)
        if cleaned and not _summary_has_raw_artifacts(cleaned):
            return cleaned
    except Exception:
        pass
    return _fallback_items_summary(items, empty_message)


def _summary_has_raw_artifacts(text: str) -> bool:
    lowered = text.lower()
    return (
        "http://" in lowered
        or "https://" in lowered
        or " | " in text
        or text.count('"') % 2 == 1
        or "skip to main content" in lowered
    )


def _normalized_compare_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _dedupe_sentences(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
    kept: list[str] = []
    seen: list[str] = []
    for sentence in sentences:
        cleaned = sentence.strip()
        if not cleaned:
            continue
        normalized = _normalized_compare_text(cleaned)
        if not normalized:
            continue
        if any(normalized == previous or normalized in previous or previous in normalized for previous in seen):
            continue
        kept.append(cleaned)
        seen.append(normalized)
    return " ".join(kept).strip()


def _is_title_heavy_answer(text: str, items: list[dict]) -> bool:
    if not text or not items:
        return False
    answer = _normalized_compare_text(text)
    title = _normalized_compare_text(_clean_news_title(items[0].get("title", "")))
    if not answer or not title:
        return False
    if answer == title:
        return True
    return answer.startswith(title) and len(answer.split()) <= len(title.split()) + 8


def _clean_spoken_result(text: str) -> str:
    cleaned = _dedupe_sentences(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _get_exa_api_key() -> str:
    return os.environ.get("EXA_API_KEY", "").strip() or EXA_API_KEY.strip()


def _cosine_sim(a: list, b: list) -> float:
    """Cosine similarity between two embedding vectors."""
    a_vec, b_vec = np.array(a), np.array(b)
    denom = np.linalg.norm(a_vec) * np.linalg.norm(b_vec)
    return float(np.dot(a_vec, b_vec) / denom) if denom else 0.0


def _embed(text: str) -> list:
    """Get embedding from the active Ollama backend."""
    from butler_config import EMBED_MODEL

    try:
        url, headers, _backend = _get_request_target_for_model(EMBED_MODEL)
        response = requests.post(
            url.replace("/api/generate", "/api/embeddings"),
            json={"model": EMBED_MODEL, "prompt": text[:500]},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("embedding", [])
    except Exception:
        return []


def _jina_fetch(url: str) -> str:
    """Fetch clean text from any URL via Jina Reader."""
    try:
        response = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/plain", "X-Return-Format": "text"},
            timeout=10,
        )
        return response.text[:600] if response.status_code == 200 else ""
    except Exception:
        return ""


def _searxng_available(force_refresh: bool = False) -> bool:
    global _SEARXNG_AVAILABLE
    if _SEARXNG_AVAILABLE is not None and not force_refresh:
        return _SEARXNG_AVAILABLE

    from butler_config import SEARXNG_URL

    try:
        response = requests.get(f"{SEARXNG_URL}/", timeout=0.5)
        _SEARXNG_AVAILABLE = response.status_code == 200
    except Exception:
        _SEARXNG_AVAILABLE = False
    return bool(_SEARXNG_AVAILABLE)


def _searxng_search(query: str, num: int = 8, categories: str = "general") -> list:
    """Fetch raw results from local SearXNG."""
    global _SEARXNG_AVAILABLE
    from butler_config import SEARXNG_URL

    if not _searxng_available():
        return []

    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "categories": categories,
                "language": "en",
            },
            timeout=1.5,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            }
            for item in results[:num]
        ]
    except Exception:
        _SEARXNG_AVAILABLE = False
        return []


def _exa_search(query: str, num: int = 5) -> list:
    """Premium path using Exa when configured."""
    exa_key = _get_exa_api_key()
    if not exa_key:
        return []

    try:
        response = requests.post(
            "https://api.exa.ai/search",
            headers={
                "x-api-key": exa_key,
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "type": "auto",
                "numResults": num,
                "contents": {
                    "highlights": {"maxCharacters": 400},
                },
            },
            timeout=8,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": (
                    item.get("highlights", [""])[0]
                    if item.get("highlights")
                    else item.get("text", "")[:400]
                ),
            }
            for item in results
        ]
    except Exception:
        return []


def _duckduckgo_search(query: str, num: int = 5) -> list:
    """Free fallback search when local SearXNG is unavailable."""
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_redirect": 1,
                "no_html": 1,
                "skip_disambig": 1,
                "t": "burry-butler",
            },
            timeout=4,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    results: list[dict] = []

    abstract = str(payload.get("Abstract", "")).strip()
    abstract_url = str(payload.get("AbstractURL", "")).strip()
    heading = str(payload.get("Heading", "")).strip() or query
    if abstract:
        results.append(
            {
                "title": heading,
                "url": abstract_url,
                "content": abstract,
            }
        )

    def add_topic(topic: dict) -> None:
        text = str(topic.get("Text", "")).strip()
        url = str(topic.get("FirstURL", "")).strip()
        if not text:
            return
        title = url.rstrip("/").split("/")[-1].replace("_", " ").strip() if url else query
        results.append(
            {
                "title": title or query,
                "url": url,
                "content": text,
            }
        )

    related = payload.get("RelatedTopics", [])
    for topic in related:
        if len(results) >= num:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            add_topic(topic)
            continue
        for nested in topic.get("Topics", []) if isinstance(topic, dict) else []:
            if len(results) >= num:
                break
            if isinstance(nested, dict):
                add_topic(nested)

    return results[:num]


def _collect_search_items(query: str, count: int = 5, categories: str = "general") -> tuple[list[dict], list[str]]:
    sources: list[str] = []
    seen: set[str] = set()
    items: list[dict] = []

    def add_results(results: list[dict], source: str) -> None:
        if not results:
            return
        if source not in sources:
            sources.append(source)
        for result in results:
            title = str(result.get("title", "")).strip()
            url = str(result.get("url", "")).strip()
            key = url or title.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "content": str(result.get("content", "")).strip(),
                    "query": query,
                }
            )
            if len(items) >= count:
                break

    # Search policy: local-first via SearXNG, then free DuckDuckGo, then premium Exa.
    add_results(_searxng_search(query, num=max(5, count), categories=categories), "searxng")
    if len(items) < count:
        add_results(_duckduckgo_search(query, num=max(5, count)), "duckduckgo")
    if len(items) < count:
        add_results(_exa_search(query, num=max(5, count)), "exa")

    return items, sources


def _domain_label(url: str) -> str:
    hostname = urllib.parse.urlparse(str(url or "")).netloc.lower()
    hostname = re.sub(r"^www\.", "", hostname)
    return hostname or "source"


def _clean_article_excerpt(text: str, max_chars: int = 600) -> str:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        cleaned = " ".join(raw_line.replace("#", " ").split()).strip(" -")
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered.startswith(("title:", "url source:", "markdown content:", "published time:", "description:")):
            continue
        if any(
            phrase in lowered
            for phrase in (
                "skip to main content",
                "main content",
                "feed global",
                "home innovation",
                "products and platforms",
                "company news",
            )
        ):
            continue
        if len(cleaned) < 35 and any(token in lowered for token in ("cookie", "subscribe", "sign in", "menu")):
            continue
        if cleaned.startswith(("!", "[")):
            continue
        lines.append(cleaned)
        if len(" ".join(lines)) >= max_chars:
            break

    if not lines:
        return ""

    excerpt = " ".join(lines)
    excerpt = re.sub(r"\s+", " ", excerpt).strip()
    if len(excerpt) <= max_chars:
        return excerpt
    truncated = excerpt[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{truncated}..." if truncated else excerpt[:max_chars]


def _clean_news_title(title: str) -> str:
    cleaned = " ".join(str(title or "").split()).strip(" -:")
    cleaned = re.split(r"\s+\|\s+", cleaned, maxsplit=1)[0]
    cleaned = re.split(r"\s+-\s+(?:google blog|youtube|reuters|ap news|al jazeera|the keyword)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    return cleaned.strip(" -:")


def _collect_news_items(topic: str, count: int = 3) -> tuple[list[dict], list[str]]:
    search_query = f"{topic} latest news"
    items, sources = _collect_search_items(search_query, count=max(5, count * 2), categories="news")
    if not items:
        items, sources = _collect_search_items(search_query, count=max(5, count * 2))
    if not items:
        items, sources = _collect_search_items(topic, count=max(5, count * 2))

    enriched: list[dict] = []
    for item in items:
        url = str(item.get("url", "")).strip()
        article_text = _clean_article_excerpt(_jina_fetch(url)) if url else ""
        snippet = str(item.get("content", "")).strip()
        if not article_text and not snippet:
            continue
        enriched.append(
            {
                **item,
                "source": _domain_label(url),
                "article_text": article_text,
            }
        )
        if len(enriched) >= count:
            break

    return enriched, sources


def _fallback_news_summary(items: list[dict], topic: str) -> str:
    if not items:
        return f"I couldn't fetch live {topic} news right now."

    lines = []
    for item in items[:3]:
        title = _clean_news_title(item.get("title", "")) or "Untitled"
        source = str(item.get("source", "")).strip() or _domain_label(item.get("url", ""))
        if title and title != "Untitled":
            lines.append(f"{title} ({source})")
        else:
            detail = str(item.get("content", "")).strip() or str(item.get("article_text", "")).strip()
            detail = re.split(r"(?<=[.!?])\s+", detail, maxsplit=1)[0].strip() or detail
            detail = _limit_words(detail, limit=14)
            lines.append(f"{source}: {detail}" if detail else source)
    return "; ".join(lines)


def _fallback_search_answer(query: str, items: list[dict]) -> str:
    if not items:
        return f"I couldn't look that up right now: {query}"

    for item in items[:3]:
        title = _clean_news_title(item.get("title", "")) or "I found a result"
        title_norm = _normalized_compare_text(title)
        title_parts = [part.strip(" -:.") for part in title.split(":", 1)]
        launch_match = re.search(
            r"\b(?:unveils|launches|introduces|debuts|releases)\s+(.+)$",
            title_parts[0],
            flags=re.IGNORECASE,
        )
        if "new product" in query.lower() and launch_match:
            product = launch_match.group(1).strip(" -:.")
            product_norm = _normalized_compare_text(product)
            descriptor = title_parts[1] if len(title_parts) > 1 else ""
            descriptor = re.split(r"\s+[—-]\s+[^—-]+$", descriptor, maxsplit=1)[0].strip()
            descriptor = _limit_words(descriptor, limit=14)
            if product_norm not in {"a new product", "new product", "a product", "product"} and product and descriptor:
                return f"The new product looks like {product}. {descriptor}"
            if product_norm not in {"a new product", "new product", "a product", "product"} and product:
                return f"The new product looks like {product}."
        detail = _clean_article_excerpt(str(item.get("content", "")).strip(), max_chars=220)
        detail = re.split(r"(?<=[.!?])\s+", detail, maxsplit=1)[0].strip() or detail
        detail = _limit_words(detail, limit=16)
        detail_norm = _normalized_compare_text(detail)
        if detail and detail_norm and detail_norm != title_norm and detail_norm not in title_norm:
            return f"{title}. {detail}"
        source = _domain_label(item.get("url", ""))
        if title:
            return f"{title} ({source})."
    return "I found a result."


def _fetch_json(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 8) -> object:
    response = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _fetch_hackernews_items(limit: int = 10) -> list[dict]:
    try:
        story_ids = _fetch_json("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=8)
        items: list[dict] = []
        for story_id in list(story_ids or [])[: max(10, limit)]:
            story = _fetch_json(
                f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                timeout=8,
            )
            if not isinstance(story, dict):
                continue
            score = int(story.get("score") or 0)
            if score <= 100:
                continue
            items.append(
                {
                    "title": str(story.get("title", "")).strip(),
                    "url": str(story.get("url", "") or f"https://news.ycombinator.com/item?id={story_id}").strip(),
                    "score": score,
                    "comments": int(story.get("descendants") or 0),
                    "by": str(story.get("by", "")).strip(),
                    "id": story_id,
                }
            )
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


def _fetch_reddit_items(subreddits: list[str], limit: int = 5) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for subreddit in subreddits:
        try:
            payload = _fetch_json(
                f"https://www.reddit.com/r/{subreddit}/hot.json",
                params={"limit": limit},
                headers=REDDIT_HEADERS,
                timeout=8,
            )
        except Exception:
            continue
        children = (
            payload.get("data", {}).get("children", [])
            if isinstance(payload, dict)
            else []
        )
        for child in children:
            post = child.get("data", {}) if isinstance(child, dict) else {}
            score = int(post.get("score") or 0)
            if score <= 200:
                continue
            permalink = str(post.get("permalink", "")).strip()
            url = str(post.get("url", "")).strip() or (
                f"https://www.reddit.com{permalink}" if permalink else ""
            )
            title = str(post.get("title", "")).strip()
            key = url or title.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "subreddit": subreddit,
                    "title": title,
                    "url": url,
                    "score": score,
                    "comments": int(post.get("num_comments") or 0),
                }
            )
    items.sort(key=lambda item: (int(item.get("score") or 0), int(item.get("comments") or 0)), reverse=True)
    return items[: max(1, limit)]


def _fetch_github_trending_items(language: str = "python", since: str = "daily", limit: int = 5) -> list[dict]:
    try:
        response = requests.get(
            f"https://github.com/trending/{language}",
            params={"since": since},
            headers=GITHUB_HEADERS,
            timeout=4,
        )
        response.raise_for_status()
        items: list[dict] = []
        seen: set[str] = set()
        blocks = re.findall(r'<article class="Box-row">(.*?)</article>', response.text, re.S)
        for block in blocks:
            repo_match = re.search(r'<h2[^>]*>.*?href="/([^"#?]+/[^"#?]+)"', block, re.S)
            if not repo_match:
                continue
            full_name = repo_match.group(1).strip()
            if not full_name or full_name in seen:
                continue
            seen.add(full_name)
            desc_match = re.search(r'<p[^>]*class="[^"]*color-fg-muted[^"]*"[^>]*>(.*?)</p>', block, re.S)
            desc = _strip_html(desc_match.group(1)) if desc_match else ""
            star_match = re.search(rf'href="/{re.escape(full_name)}/stargazers"[^>]*>(.*?)</a>', block, re.S)
            star_text = _strip_html(star_match.group(1)) if star_match else ""
            stars = int(star_text.replace(",", "")) if star_text.replace(",", "").isdigit() else None
            items.append(
                {
                    "title": full_name,
                    "url": f"https://github.com/{full_name}",
                    "description": desc,
                    "score": stars,
                    "language": language,
                }
            )
            if len(items) >= limit:
                break
        if items:
            return items
    except Exception:
        pass

    try:
        response = requests.get(
            "https://api.gitterapp.com/repositories",
            params={"language": language, "since": since},
            headers=GITHUB_HEADERS,
            timeout=2,
        )
        response.raise_for_status()
        data = response.json()
        items = []
        for repo in data[:limit]:
            name = str(repo.get("name", "")).strip()
            author = str(repo.get("author", "")).strip()
            full_name = f"{author}/{name}".strip("/") if author else name
            items.append(
                {
                    "title": full_name,
                    "url": str(repo.get("url", "")).strip() or f"https://github.com/{full_name}",
                    "description": str(repo.get("description", "")).strip(),
                    "score": int(repo.get("stars", 0) or 0),
                    "language": str(repo.get("language", language)).strip() or language,
                }
            )
        if items:
            return items
    except Exception:
        pass

    try:
        text = _jina_fetch(f"https://github.com/trending/{language}?since={since}")
        items = []
        seen: set[str] = set()
        for line in text.splitlines():
            cleaned = " ".join(line.split()).strip()
            if "/" not in cleaned or cleaned.startswith("http"):
                continue
            repo_match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", cleaned)
            if not repo_match:
                continue
            full_name = repo_match.group(1)
            if full_name in seen:
                continue
            seen.add(full_name)
            description = ""
            if " - " in cleaned:
                description = cleaned.split(" - ", 1)[1].strip()
            items.append(
                {
                    "title": full_name,
                    "url": f"https://github.com/{full_name}",
                    "description": description,
                    "score": None,
                    "language": language,
                }
            )
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


def _strip_html(fragment: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _market_signal_keywords(topics: list[str]) -> set[str]:
    keywords = {
        "ai",
        "agent",
        "agents",
        "llm",
        "llms",
        "model",
        "models",
        "open source",
        "open-source",
        "oss",
        "inference",
        "local",
        "rag",
    }
    for topic in topics:
        lowered = str(topic).lower()
        if "open source" in lowered:
            keywords.update({"github", "repo", "framework"})
        if "agent" in lowered:
            keywords.update({"automation", "tooling"})
    return keywords


def _matches_market_signal(text: str, keywords: set[str]) -> bool:
    lowered = str(text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def _collect_market_fallback_items(topics: list[str]) -> tuple[list[dict], list[str]]:
    keywords = _market_signal_keywords(topics)
    items: list[dict] = []
    seen: set[str] = set()
    sources: list[str] = []

    def add_item(source: str, item: dict, *, query: str) -> None:
        key = str(item.get("url") or item.get("title", "")).strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        payload = dict(item)
        payload["query"] = query
        payload["source"] = source
        payload["content"] = str(item.get("content") or item.get("description") or "").strip()
        items.append(payload)
        if source not in sources:
            sources.append(source)

    for item in _fetch_reddit_items(["MachineLearning", "LocalLLaMA", "programming"], limit=3):
        add_item("reddit", item, query="community signals")

    hn_items = _fetch_hackernews_items(limit=4)
    filtered_hn = [item for item in hn_items if _matches_market_signal(item.get("title", ""), keywords)]
    for item in (filtered_hn or hn_items[:2])[:2]:
        add_item("hackernews", item, query="hacker news")

    gh_items = _fetch_github_trending_items(language="python", since="daily", limit=3)
    filtered_gh = [
        item
        for item in gh_items
        if _matches_market_signal(
            f"{item.get('title', '')} {item.get('description', '')}",
            keywords,
        )
    ]
    for item in (filtered_gh or gh_items[:2])[:2]:
        add_item("github_trending", item, query="trending repos")

    return _truncate_items(items, limit=5), sources


def run_agent(agent_type: str, input_data: dict) -> dict:
    """
    Run a specialist agent and return structured results.

    agent_type:
      news | vps | memory | code | search | github | bugfinder
    """
    model = _pick_model(agent_type)
    print(f"[Agent/{agent_type}] Using model: {model}")

    try:
        if agent_type == "news":
            return _news_agent(input_data, model)
        if agent_type == "vps":
            return _vps_agent(input_data, model)
        if agent_type == "memory":
            return _memory_agent(input_data, model)
        if agent_type == "code":
            return _code_agent(input_data, model)
        if agent_type == "search":
            return _search_agent(input_data, model)
        if agent_type == "fetch":
            return _fetch_agent(input_data, model)
        if agent_type == "market":
            return _market_agent(input_data, model)
        if agent_type == "hackernews":
            return _hackernews_agent(input_data, model)
        if agent_type == "reddit":
            return _reddit_agent(input_data, model)
        if agent_type == "github_trending":
            return _github_trending_agent(input_data, model)
        if agent_type == "github":
            return _github_agent(input_data, model)
        if agent_type == "bugfinder":
            return _bugfinder_agent(input_data, model)
        return {"status": "error", "result": f"Unknown agent type: {agent_type}", "data": {}}
    except Exception as exc:
        print(f"[Agent/{agent_type}] Error: {exc}")
        return {"status": "error", "result": str(exc), "data": {}}


def run_agent_async(agent_type: str, input_data: dict, callback=None) -> threading.Thread:
    def _worker() -> None:
        result = run_agent(agent_type, input_data)
        try:
            note_agent_result(
                agent_type,
                str(result.get("status", "ok") or "ok"),
                str(result.get("result", "") or ""),
            )
        except Exception:
            pass
        if callback is not None:
            try:
                callback(result)
            except Exception:
                pass

    thread = threading.Thread(target=_worker, daemon=True, name=f"agent-{agent_type}")
    thread.start()
    return thread


def _news_agent(data: dict, model: str) -> dict:
    topic = data.get("topic", "AI and tech news")
    hours = data.get("hours", 24)
    global _LAST_FETCH_DATA
    _LAST_FETCH_DATA = {}
    items, sources = _collect_news_items(topic, count=3)

    if items:
        material = "\n".join(
            f"- {item.get('title', '')} ({item.get('source', '')}): "
            f"{(item.get('article_text') or item.get('content') or '')[:420]}"
            for item in items
        )
        prompt = f"""You are Butler's current news agent.
Summarize the latest developments about "{topic}" using ONLY the material below.
Return exactly 3 short bullet points.
Each bullet must mention a source in parentheses.
Keep the whole answer under 120 words.
If the coverage is thin or mixed, say that briefly instead of inventing details.

News material:
{material}
"""
        try:
            summary = _clean_spoken_result(_limit_words(_call_model(prompt, model, max_tokens=160), limit=150))
        except Exception:
            summary = ""
        if not summary or _summary_has_raw_artifacts(summary) or _is_title_heavy_answer(summary, items):
            summary = _fallback_news_summary(items, topic)
        search_data = {
            "backend": "+".join(sorted(sources)) if sources else "news_crawl",
            "tool": "news_crawl",
            "text": material,
            "items": items,
            "sources": sorted(sources),
            "topic": topic,
            "hours": hours,
        }
        _LAST_FETCH_DATA = dict(search_data)
        return {"status": "ok", "result": summary, "data": search_data}

    material = _fetch_headlines(f"{topic} last {hours} hours")
    search_data = (
        dict(_LAST_FETCH_DATA)
        if _LAST_FETCH_DATA.get("text") == material
        else {"backend": "headline_wrapper", "tool": "headlines", "text": material, "topic": topic, "hours": hours}
    )

    if not material or len(material.strip()) < 20:
        prompt = f"Summarize what you know about recent {topic} news in under 50 words."
        try:
            summary = _limit_words(_call_model(prompt, model, max_tokens=100), limit=150)
        except Exception:
            summary = f"I couldn't fetch live {topic} news right now."
        if not summary:
            summary = f"I couldn't fetch live {topic} news right now."
        return {"status": "ok", "result": summary, "data": {}}

    prompt = f"""Summarize this recent news material about "{topic}".
List the 3 most important things. Under 80 words total. Be concrete.

Material:
{material[:2200]}

Summary:"""
    summary = _clean_spoken_result(_limit_words(_call_model(prompt, model, max_tokens=160), limit=150))
    if not summary or _summary_has_raw_artifacts(summary):
        summary = _fallback_text_summary(material, f"I couldn't fetch live {topic} news right now.")
    return {"status": "ok", "result": summary, "data": search_data}


def _search_agent(data: dict, model: str) -> dict:
    query = " ".join(str(data.get("query", "")).split()).strip()
    global _LAST_FETCH_DATA
    _LAST_FETCH_DATA = {}
    if query.lower() in {"what is", "what's", "search", "find", "look up"}:
        return {"status": "ok", "result": "Tell me what to look up.", "data": {}}

    items, sources = _collect_search_items(query, count=3)
    if items:
        material = "\n".join(
            f"- {item.get('title', '')}: {str(item.get('content', ''))[:220]}"
            for item in items
        )
        prompt = f"""Answer this question directly and specifically.
Question: {query}

Material:
{material}

Answer in under 45 words. No raw URLs. Make it sound spoken, not scraped."""
        try:
            answer = _clean_spoken_result(_limit_words(_call_model(prompt, model, max_tokens=100), limit=90))
        except Exception:
            answer = ""
        if not answer or _summary_has_raw_artifacts(answer) or _is_title_heavy_answer(answer, items):
            answer = _fallback_search_answer(query, items)
        return {
            "status": "ok",
            "result": answer,
            "data": {"items": items, "sources": sorted(sources), "tool": "search_lookup", "query": query},
        }

    material = _fetch_headlines(query)
    search_data = (
        dict(_LAST_FETCH_DATA)
        if _LAST_FETCH_DATA.get("text") == material
        else {"backend": "headline_wrapper", "tool": "headlines", "text": material}
    )

    if not material or len(material.strip()) < 20:
        prompt = f"Answer this concisely in under 35 words: {query}"
        try:
            answer = _clean_spoken_result(_limit_words(_call_model(prompt, model, max_tokens=70), limit=70))
        except Exception:
            answer = ""
        if not answer:
            answer = f"I couldn't look that up right now: {query}"
        return {"status": "ok", "result": answer, "data": {}}

    prompt = f"""Answer this question directly and specifically.
Question: {query}

Material:
{material[:2200]}

Answer in under 45 words. No raw URLs. Make it sound spoken, not scraped."""
    try:
        answer = _clean_spoken_result(_limit_words(_call_model(prompt, model, max_tokens=100), limit=90))
    except Exception:
        answer = ""
    if not answer or _summary_has_raw_artifacts(answer):
        answer = _fallback_text_summary(material, f"I couldn't look that up right now: {query}")
    return {"status": "ok", "result": answer, "data": search_data}


def _fetch_agent(data: dict, model: str) -> dict:
    query = " ".join(str(data.get("query", "")).split()).strip()
    url = str(data.get("url", "")).strip()
    if not url:
        match = re.search(
            r"(https?://[^\s]+|www\.[^\s]+|\b[a-z0-9.-]+\.(?:com|org|net|io|ai|dev|app|co|in)\b)",
            query,
            flags=re.IGNORECASE,
        )
        if match:
            url = match.group(1)
    if not url:
        return {"status": "ok", "result": "Tell me which page to read.", "data": {}}
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    text = _jina_fetch(url)
    if not text or len(text.strip()) < 40:
        return {"status": "ok", "result": f"I couldn't read {url} right now.", "data": {"url": url}}

    prompt = f"""Read this fetched web page content and answer the user's request.
User request: {query or f"Read {url}"}
Source: {url}

Page content:
{text[:2600]}

Reply in under 70 words. Sound spoken and useful. Mention the source domain once if helpful."""
    try:
        summary = _clean_spoken_result(_limit_words(_call_model(prompt, model, max_tokens=140), limit=110))
    except Exception:
        summary = ""
    if not summary or _summary_has_raw_artifacts(summary):
        summary = _fallback_text_summary(text, f"I read {url}, but couldn't summarize it cleanly.")
    return {
        "status": "ok",
        "result": summary,
        "data": {"url": url, "tool": "jina_fetch", "text": text[:2600]},
    }


def _market_agent(data: dict, model: str) -> dict:
    topics = data.get("topics") or ["AI agents", "LLMs", "open source"]
    topics = [str(topic).strip() for topic in topics if str(topic).strip()]
    aggregated: list[dict] = []
    seen: set[str] = set()
    backends: set[str] = set()

    for topic in topics[:4]:
        items, sources = _collect_search_items(topic, count=3)
        backends.update(sources)
        for item in items:
            key = str(item.get("url") or item.get("title", "")).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            aggregated.append(item)

    if not aggregated:
        fallback_items, fallback_sources = _collect_market_fallback_items(topics)
        aggregated.extend(fallback_items)
        backends.update(fallback_sources)

    top_items = _truncate_items(aggregated, limit=5)
    if not top_items:
        return {
            "status": "ok",
            "result": "I couldn't pull a live AI market pulse right now.",
            "data": {"items": [], "topics": topics, "sources": sorted(backends)},
        }

    material = "\n".join(
        f"- [{item.get('query', 'topic')}] {item.get('title', '')}: {item.get('content', '')[:180]} ({item.get('url', '')})"
        for item in top_items
    )
    prompt = f"""You are Butler's market pulse agent.
Summarize the most important current signals across these topics: {", ".join(topics)}.
Return exactly 3 bullet points.
Keep the whole answer under 150 words.
Be concrete and avoid hype.

Signals:
{material}
"""
    summary = _safe_model_summary(
        prompt,
        model,
        top_items,
        empty_message="I couldn't pull a live AI market pulse right now.",
        max_tokens=120,
        timeout=4,
    )
    return {
        "status": "ok",
        "result": summary,
        "data": {"items": top_items, "topics": topics, "sources": sorted(backends)},
    }


def _hackernews_agent(data: dict, model: str) -> dict:
    limit = int(data.get("limit", 10) or 10)
    items = _fetch_hackernews_items(limit=limit)
    if not items:
        return {
            "status": "ok",
            "result": "I couldn't fetch Hacker News right now.",
            "data": {"items": []},
        }

    material = "\n".join(
        f"- {item.get('title', '')} | score {item.get('score', 0)} | {item.get('url', '')}"
        for item in items[: min(limit, 10)]
    )
    prompt = f"""Summarize what is trending on Hacker News right now.
Use 3 short bullet points.
Mention the strongest story names directly.
Stay under 120 words.

Stories:
{material}
"""
    summary = _safe_model_summary(
        prompt,
        model,
        items,
        empty_message="I couldn't fetch Hacker News right now.",
        max_tokens=160,
    )
    return {"status": "ok", "result": summary, "data": {"items": items}}


def _reddit_agent(data: dict, model: str) -> dict:
    subreddits = data.get("subreddits") or ["MachineLearning", "LocalLLaMA", "programming"]
    subreddits = [str(sub).strip() for sub in subreddits if str(sub).strip()]
    limit = int(data.get("limit", 5) or 5)
    items = _fetch_reddit_items(subreddits, limit=limit)
    if not items:
        return {
            "status": "ok",
            "result": "I couldn't pull strong Reddit signals right now.",
            "data": {"items": [], "subreddits": subreddits},
        }

    material = "\n".join(
        f"- r/{item.get('subreddit', '')}: {item.get('title', '')} | score {item.get('score', 0)} | comments {item.get('comments', 0)}"
        for item in items[:limit]
    )
    prompt = f"""Summarize what Reddit communities are saying right now.
Use 3 concise bullet points.
Focus on the strongest themes from: {", ".join(subreddits)}.
Keep it under 120 words.

Posts:
{material}
"""
    summary = _safe_model_summary(
        prompt,
        model,
        items,
        empty_message="I couldn't pull strong Reddit signals right now.",
        max_tokens=160,
    )
    return {
        "status": "ok",
        "result": summary,
        "data": {"items": items, "subreddits": subreddits},
    }


def _github_trending_agent(data: dict, model: str) -> dict:
    language = str(data.get("language", "python") or "python").strip().lower()
    since = str(data.get("since", "daily") or "daily").strip().lower()
    items = _fetch_github_trending_items(language=language, since=since, limit=5)
    if not items:
        return {
            "status": "ok",
            "result": "I couldn't fetch GitHub trending repos right now.",
            "data": {"items": [], "language": language, "since": since},
        }

    material = "\n".join(
        f"- {item.get('title', '')}: {item.get('description', '')} | stars {item.get('score', 'n/a')}"
        for item in items[:5]
    )
    prompt = f"""Summarize what is hot on GitHub trending for {language}.
Use 3 concise bullet points.
Mention the repo names directly.
Keep it under 120 words.

Trending repos:
{material}
"""
    summary = _safe_model_summary(
        prompt,
        model,
        items,
        empty_message="I couldn't fetch GitHub trending repos right now.",
        max_tokens=160,
    )
    return {
        "status": "ok",
        "result": summary,
        "data": {"items": items, "language": language, "since": since},
    }


def _fetch_search_text(query: str, count: int = 5) -> str:
    """
    Free search pipeline:
      1. SearXNG from the local search backend
      2. Semantic rerank via local embeddings
      3. Jina Reader for top result content
      4. Return ranked snippets plus top content
    """
    global _LAST_FETCH_DATA

    raw = _searxng_search(query, num=max(8, count))
    backend = "searxng"
    if not raw:
        _LAST_FETCH_DATA = {"backend": backend, "tool": "semantic", "text": ""}
        return ""

    query_vec = _embed(query)
    if query_vec:
        scored = []
        for result in raw:
            doc_text = f"{result.get('title', '')} {result.get('content', '')}"
            doc_vec = _embed(doc_text)
            score = _cosine_sim(query_vec, doc_vec) if doc_vec else 0.0
            scored.append((score, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        ranked = [result for _, result in scored]
    else:
        ranked = raw

    top_content = ""
    if ranked:
        top_content = _jina_fetch(str(ranked[0].get("url", "")).strip())

    snippets = "\n".join(
        f"{result.get('title', '')}: {str(result.get('content', ''))[:120]}".strip(": ")
        for result in ranked[:4]
    ).strip()
    text = f"{snippets}\n\nTop result:\n{top_content[:400]}".strip() if top_content else snippets
    _LAST_FETCH_DATA = {"backend": backend, "tool": "semantic", "text": text}
    return text


def _fetch_headlines(query: str) -> str:
    global _LAST_FETCH_DATA
    fetched = _fetch_search_text(query, count=6)
    if isinstance(fetched, dict):
        _LAST_FETCH_DATA = dict(fetched)
        return _LAST_FETCH_DATA.get("text", "")
    if isinstance(fetched, str):
        if not _LAST_FETCH_DATA:
            _LAST_FETCH_DATA = {"backend": "semantic", "tool": "search", "text": fetched}
        return fetched
    _LAST_FETCH_DATA = {"backend": "semantic", "tool": "search", "text": ""}
    return ""


def _resolve_ssh_target(host: str) -> str:
    if "@" in host:
        return host
    secret = get_vps_secret(host)
    username = str(secret.get("username", "")).strip()
    return f"{username}@{host}" if username else host


def _vps_agent(data: dict, model: str) -> dict:
    host = data.get("host", "")
    if not host:
        return {"status": "error", "result": "No VPS host configured", "data": {}}

    resolved_host = _resolve_ssh_target(host)
    commands = [
        "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
        "df -h / | tail -1",
        "free -h | grep Mem",
        "uptime",
    ]

    secret = get_vps_secret(host)
    raw_outputs = []
    for command in commands:
        shell_cmd = ["ssh", "-o", "ConnectTimeout=8", resolved_host, command]
        if secret.get("password") and shutil.which("sshpass"):
            shell_cmd = ["sshpass", "-p", secret["password"], *shell_cmd]

        try:
            result = subprocess.run(
                shell_cmd,
                capture_output=True,
                text=True,
                timeout=20,
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if stdout or stderr:
                block = stdout or stderr
                raw_outputs.append(f"$ {command}\n{block}")
        except Exception as exc:
            raw_outputs.append(f"$ {command}\nFailed: {exc}")

    if not raw_outputs:
        return {"status": "error", "result": "Could not connect to VPS", "data": {}}

    raw = "\n\n".join(raw_outputs)
    prompt = f"""You are analyzing VPS status output.
Summarize what is running, what looks healthy, and what needs attention.
Under 60 words. Name containers explicitly when present.

Raw output:
{raw[:2200]}

Plain English summary:"""
    summary = _call_model(prompt, model, max_tokens=120)
    return {"status": "ok", "result": summary, "data": {"raw": raw[:2400], "host": resolved_host}}


def _memory_agent(data: dict, model: str) -> dict:
    sessions = data.get("sessions", [])
    if not sessions:
        return {"status": "ok", "result": "Nothing to compress", "data": {}}

    session_text = "\n".join(
        [
            f"- {session.get('timestamp', '')[:16]}: {session.get('speech', '')[:100]}"
            for session in sessions[-10:]
        ]
    )

    prompt = f"""Compress these Butler sessions into 3 key memory points.
Each point must stay under 120 characters and start with the date.

Sessions:
{session_text}

3 memory points:"""
    summary = _call_model(prompt, model, max_tokens=200)
    points = [line.strip("- *").strip() for line in summary.splitlines() if line.strip()]
    return {"status": "ok", "result": summary, "data": {"points": points[:3]}}


def _code_agent(data: dict, model: str) -> dict:
    task = data.get("task", "")
    context = data.get("context", "")
    language = data.get("language", "python")

    prompt = f"""Write {language} code for this task.
Task: {task}
Context: {context}

Output only the code:"""
    code = _call_model(prompt, model, max_tokens=600)
    return {"status": "ok", "result": code, "data": {"language": language}}


def _github_agent(data: dict, model: str) -> dict:
    tool_name = data.get("tool", "")
    arguments = data.get("arguments", {}) if isinstance(data.get("arguments"), dict) else {}
    question = data.get("question", "")

    if not tool_name:
        tools = list_server_tools("github")
        names = [tool.get("name", "") for tool in tools if tool.get("name")]
        result = "Available GitHub MCP tools: " + ", ".join(names[:12]) if names else "No GitHub MCP tools available"
        return {"status": "ok", "result": result, "data": {"tools": names[:20]}}

    result = call_server_tool(
        "github",
        arguments=arguments,
        preferred_tool=tool_name,
        hints=["repo", "pull", "issue", "github"],
    )
    raw_text = normalize_tool_result(result)
    if not question:
        return {
            "status": "ok",
            "result": raw_text[:1000] or "GitHub MCP call returned no text",
            "data": {"tool": tool_name},
        }

    prompt = f"""Answer this GitHub question directly.
Question: {question}

GitHub tool output:
{raw_text[:2600]}

Answer in under 80 words:"""
    answer = _call_model(prompt, model, max_tokens=140)
    return {"status": "ok", "result": answer, "data": {"tool": tool_name}}


def _bugfinder_agent(data: dict, model: str) -> dict:
    logs = data.get("logs", "")
    if isinstance(logs, list):
        logs = "\n".join(str(item) for item in logs)
    target = data.get("target", "system")
    scope = data.get("scope", "quick")

    if not logs:
        logs = json.dumps(data, indent=2)

    prompt = f"""You are Butler's bug finder.
Analyze these diagnostics for target "{target}" (scope: {scope}).
Return the top bugs or regressions, likely root cause, and next fix.
Under 120 words. Be specific.

Diagnostics:
{logs[:3200]}

Bug summary:"""
    summary = _call_model(prompt, model, max_tokens=220)
    return {"status": "ok", "result": summary, "data": {"target": target, "scope": scope}}


if __name__ == "__main__":
    print("=== Specialist Agent Tests ===\n")

    failures = 0
    for agent_name, payload in [
        ("news", {"topic": "AI agents 2026", "hours": 24}),
        ("search", {"query": "what is Qwen2.5 model"}),
        (
            "memory",
            {
                "sessions": [
                    {"timestamp": "2026-04-04T01:30", "speech": "Still grinding on mac-butler executor"},
                    {"timestamp": "2026-04-04T02:00", "speech": "Fixed voice layer, now using Samantha"},
                    {"timestamp": "2026-04-04T13:00", "speech": "Back at it, wiring multi-agent system"},
                ]
            },
        ),
    ]:
        print(f"Testing {agent_name} agent...")
        result = run_agent(agent_name, payload)
        print(f"  Status: {result['status']}")
        print(f"  Result: {result['result'][:180]}\n")
        if result["status"] != "ok":
            failures += 1

    raise SystemExit(0 if failures == 0 else 1)
