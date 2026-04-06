#!/usr/bin/env python3
"""Live browsing agent for Burry's browse_web tool path."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import requests

from brain.ollama_client import _call, pick_butler_model
from butler_config import SEARXNG_URL
from butler_secrets.loader import get_secret

USER_AGENT = "BurryBrowser/1.0"


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "").strip() or url
    except Exception:
        return url


def _clip_text(text: str, limit: int = 10000) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _fallback_summary(question: str, pages: list[dict]) -> str:
    if not pages:
        return f"I couldn't pull useful web results for {question}."
    lead = pages[0]
    title = str(lead.get("title", "")).strip() or _domain(str(lead.get("url", "")))
    source = _domain(str(lead.get("url", "")))
    snippet = _clip_text(lead.get("text", "") or lead.get("content", ""), limit=180)
    if snippet:
        return f"{title} from {source}: {snippet}"
    return f"I found {title} on {source}, but the page content was thin."


class BrowsingAgent:
    def __init__(self, model: str | None = None):
        self.model = model or pick_butler_model("voice")

    def search(self, query: str, question: str | None = None) -> dict:
        clean_query = " ".join(str(query or "").split()).strip()
        if not clean_query:
            return {"status": "ok", "result": "Tell me what to search for.", "data": {"items": [], "sources": []}}

        prompt_question = question or clean_query
        items, sources = self._search_urls(clean_query)
        pages = []
        for item in items[:3]:
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            text = self._fetch(url, query=prompt_question)
            if not text:
                continue
            pages.append(
                {
                    "title": str(item.get("title", "")).strip() or _domain(url),
                    "url": url,
                    "content": str(item.get("content", "")).strip(),
                    "text": text,
                }
            )

        summary = self._summarize_search(prompt_question, pages)
        if not summary:
            summary = _fallback_summary(prompt_question, pages or items)

        return {
            "status": "ok",
            "result": summary,
            "data": {
                "query": clean_query,
                "tool": "browser_search",
                "items": [
                    {
                        "title": page.get("title", ""),
                        "url": page.get("url", ""),
                        "source": _domain(str(page.get("url", ""))),
                    }
                    for page in (pages or items)[:3]
                ],
                "sources": sources,
            },
        }

    def fetch(self, url: str, question: str) -> dict:
        clean_url = " ".join(str(url or "").split()).strip()
        if not clean_url:
            return {"status": "ok", "result": "Tell me which page to read.", "data": {}}
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        text = self._fetch(clean_url, query=question or clean_url)
        if not text:
            return {
                "status": "ok",
                "result": f"I couldn't read {_domain(clean_url)} right now.",
                "data": {"url": clean_url, "tool": "browser_fetch"},
            }

        prompt = f"""Read this web page and answer the user's question directly.
Question: {question or f"Read {clean_url}"}
Source: {clean_url}

Page:
{text[:8000]}

Reply in under 80 words. Mention the source domain once if useful. Sound spoken, not scraped."""
        try:
            summary = _clip_text(
                _call(prompt, self.model, temperature=0.2, max_tokens=160),
                limit=180,
            )
        except Exception:
            summary = ""
        if not summary:
            summary = _fallback_summary(question or clean_url, [{"title": _domain(clean_url), "url": clean_url, "text": text}])

        return {
            "status": "ok",
            "result": summary,
            "data": {
                "url": clean_url,
                "tool": "browser_fetch",
                "source": _domain(clean_url),
            },
        }

    def _summarize_search(self, question: str, pages: list[dict]) -> str:
        if not pages:
            return ""
        material = "\n\n".join(
            (
                f"Title: {page.get('title', '')}\n"
                f"URL: {page.get('url', '')}\n"
                f"Text: {str(page.get('text', '') or page.get('content', ''))[:2800]}"
            )
            for page in pages[:3]
        )
        prompt = f"""Answer this web question directly.
Question: {question}

Material from the top pages:
{material}

Give one spoken answer in under 90 words. No raw URLs. Synthesize across sources if needed."""
        try:
            return _clip_text(_call(prompt, self.model, temperature=0.2, max_tokens=180), limit=220)
        except Exception:
            return ""

    def _search_urls(self, query: str) -> tuple[list[dict], list[str]]:
        results = self._searxng(query)
        if results:
            return results, ["searxng"]
        results = self._duckduckgo(query)
        if results:
            return results, ["duckduckgo"]
        results = self._exa(query)
        if results:
            return results, ["exa"]
        return [], []

    def _searxng(self, query: str) -> list[dict]:
        try:
            response = requests.get(
                f"{SEARXNG_URL}/search",
                params={"q": query, "format": "json", "language": "en"},
                timeout=2,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        return [
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "content": str(item.get("content", "")).strip(),
            }
            for item in payload.get("results", [])[:5]
            if str(item.get("url", "")).strip()
        ]

    def _duckduckgo(self, query: str) -> list[dict]:
        try:
            response = requests.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_redirect": 1,
                    "no_html": 1,
                    "skip_disambig": 1,
                    "t": "burry-browser",
                },
                timeout=4,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        items = []
        abstract = str(payload.get("Abstract", "")).strip()
        abstract_url = str(payload.get("AbstractURL", "")).strip()
        if abstract and abstract_url:
            items.append(
                {
                    "title": str(payload.get("Heading", "")).strip() or query,
                    "url": abstract_url,
                    "content": abstract,
                }
            )
        for topic in payload.get("RelatedTopics", []):
            if len(items) >= 5:
                break
            if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
                items.append(
                    {
                        "title": str(topic.get("FirstURL", "")).rstrip("/").split("/")[-1].replace("_", " ").strip() or query,
                        "url": str(topic.get("FirstURL", "")).strip(),
                        "content": str(topic.get("Text", "")).strip(),
                    }
                )
        return items

    def _exa(self, query: str) -> list[dict]:
        api_key = get_secret("EXA_API_KEY")
        if not api_key:
            return []
        try:
            response = requests.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "type": "auto",
                    "numResults": 5,
                    "contents": {"highlights": {"maxCharacters": 300}},
                },
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        return [
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "content": (
                    str(item.get("highlights", [""])[0]).strip()
                    if item.get("highlights")
                    else str(item.get("text", "")).strip()[:300]
                ),
            }
            for item in payload.get("results", [])[:5]
            if str(item.get("url", "")).strip()
        ]

    def _run_async(self, coroutine) -> str:
        try:
            return asyncio.run(coroutine)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coroutine)
            finally:
                loop.close()

    def _fetch(self, url: str, query: str = "") -> str:
        text = self._fetch_via_scrapling(url)
        if not text:
            text = self._fetch_via_scrapling_stealth(url)
        if not text:
            text = self._fetch_via_playwright(url)
        if text:
            clean = self._fetch_via_crawl4ai(url, query=query)
            if clean:
                return clean
            return text
        text = self._fetch_via_crawl4ai(url, query=query)
        if text:
            return text
        text = self._fetch_via_jina(url)
        if text:
            return text
        return self._fetch_via_requests(url)

    def _fetch_via_scrapling(self, url: str) -> str:
        try:
            from scrapling.fetchers import Fetcher
        except Exception:
            return ""

        try:
            page = Fetcher.get(url, stealthy_headers=True, follow_redirects=True, timeout=8000)
            return _clip_text(page.get_all_text(separator="\n"), limit=10000)
        except Exception:
            return ""

    def _fetch_via_scrapling_stealth(self, url: str) -> str:
        try:
            from scrapling.fetchers import StealthyFetcher
        except Exception:
            return ""

        try:
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=12000)
            return _clip_text(page.get_all_text(separator="\n"), limit=10000)
        except Exception:
            return ""

    def _fetch_via_crawl4ai(self, url: str, query: str = "") -> str:
        if not query:
            return ""
        try:
            from crawl4ai import AsyncWebCrawler
            from crawl4ai.content_filter_strategy import BM25ContentFilter
        except Exception:
            return ""

        async def _crawl() -> str:
            try:
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(
                        url=url,
                        word_count_threshold=10,
                        content_filter=BM25ContentFilter(
                            user_query=query,
                            bm25_threshold=1.2,
                        ),
                        bypass_cache=True,
                    )
                if not getattr(result, "success", False):
                    return ""
                return _clip_text(getattr(result, "markdown", "") or "", limit=8000)
            except Exception:
                return ""

        return self._run_async(_crawl())

    def _fetch_via_playwright(self, url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return ""

        try:
            with sync_playwright() as playwright:
                text = ""
                launchers = [
                    lambda: playwright.chromium.launch(headless=True, channel="chrome"),
                    lambda: playwright.chromium.launch(headless=True),
                ]
                for launch_browser in launchers:
                    browser = None
                    try:
                        browser = launch_browser()
                        page = browser.new_page()
                        page.goto(url, wait_until="domcontentloaded", timeout=8000)
                        text = page.locator("body").inner_text(timeout=2000)
                        break
                    except Exception:
                        text = ""
                    finally:
                        if browser is not None:
                            try:
                                browser.close()
                            except Exception:
                                pass
                if not text:
                    return ""
        except Exception:
            return ""
        return _clip_text(text, limit=10000)

    def _fetch_via_jina(self, url: str) -> str:
        try:
            response = requests.get(
                f"https://r.jina.ai/{url}",
                headers={"Accept": "text/plain", "X-Return-Format": "text"},
                timeout=10,
            )
            if response.status_code != 200:
                return ""
            return _clip_text(response.text, limit=10000)
        except Exception:
            return ""

    def _fetch_via_requests(self, url: str) -> str:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=8,
            )
            response.raise_for_status()
        except Exception:
            return ""
        text = re.sub(r"<script[\s\S]*?</script>", " ", response.text, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return _clip_text(text, limit=10000)
