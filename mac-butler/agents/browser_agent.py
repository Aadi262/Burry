#!/usr/bin/env python3
"""Browser agent wrappers with an AgentScope BrowserAgent fallback path."""
from __future__ import annotations

import asyncio
import re


def _extract_task_url(task: str) -> str:
    raw = str(task or "").strip()
    if not raw:
        return ""
    explicit = re.search(r"https?://\S+", raw, flags=re.IGNORECASE)
    if explicit:
        return explicit.group(0).rstrip(".,)")
    bare = re.search(
        r"\b(?:www\.)?[a-z0-9.-]+\.(?:com|org|net|io|ai|dev|app|co|in)(?:/[^\s]*)?",
        raw,
        flags=re.IGNORECASE,
    )
    if not bare:
        return ""
    return f"https://{bare.group(0).rstrip('.,)')}"


def _github_latest_commit_summary(task: str, page_text: str) -> str:
    lowered = str(task or "").lower()
    if "latest commit" not in lowered or "github" not in lowered:
        return ""
    lines = [line.strip() for line in str(page_text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lower() != "latest commit":
            continue
        window = lines[index + 1:index + 8]
        for offset, candidate in enumerate(window):
            if re.fullmatch(r"[0-9a-f]{7,40}", candidate.lower()):
                continue
            if candidate.lower() in {"history", "code", "issues", "pull requests"}:
                continue
            if offset == 0 and re.fullmatch(r"[a-z0-9_.-]+", candidate.lower()):
                continue
            return f"The latest commit message is: {candidate}"
    match = re.search(
        r"Latest commit\s+.+?\s+([^\n]+?)\s+[0-9a-f]{7,40}\b",
        str(page_text or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return f"The latest commit message is: {match.group(1).strip()}"
    return ""


async def _browse_and_act_custom(task: str, model_name: str = "gemma4:e4b") -> str:
    """Fallback browser task execution using Playwright or the legacy browser agent."""
    try:
        from playwright.async_api import async_playwright

        from brain.ollama_client import _call

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()

            target_url = _extract_task_url(task)
            if target_url:
                await page.goto(target_url, wait_until="networkidle", timeout=10000)
            elif any(kw in task.lower() for kw in ["github", "hackernews", "hn ", "reddit", "mail.google"]):
                for site, url in [
                    ("github", "https://github.com"),
                    ("hacker news", "https://news.ycombinator.com"),
                    (" hn ", "https://news.ycombinator.com"),
                    ("reddit", "https://www.reddit.com"),
                    ("mail.google", "https://mail.google.com"),
                ]:
                    if site in task.lower():
                        await page.goto(url, wait_until="networkidle", timeout=10000)
                        break

            text = await page.evaluate("document.body.innerText")
            await browser.close()

            github_commit = _github_latest_commit_summary(task, text)
            if github_commit:
                return github_commit

            result = _call(
                f"Task: {task}\n\nPage content:\n{text[:2000]}\n\nAnswer the task concisely:",
                model_name,
                max_tokens=200,
                temperature=0.1,
            )
            return result or text[:500]

    except Exception as exc:
        try:
            from browser.agent import BrowsingAgent

            result = BrowsingAgent().search(task, question=task)
            return result.get("result", f"Browser error: {exc}")
        except Exception:
            return f"Browser unavailable: {exc}"


async def browse_and_act(task: str, model_name: str = "gemma4:e4b") -> str:
    """Async browser task entrypoint backed by the custom fallback implementation."""
    return await _browse_and_act_custom(task, model_name=model_name)


def _sync_browse_custom(task: str) -> str:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_browse_and_act_custom(task))
    finally:
        loop.close()


def sync_browse(task: str) -> str:
    """Browse using AgentScope BrowserAgent if available, custom fallback otherwise."""
    try:
        from agentscope.agents import BrowserAgent
        from agentscope.formatter import OllamaChatFormatter
        from agentscope.message import Msg

        from brain.agentscope_backbone import _get_persistent_loop, ensure_agentscope_initialized
        from brain.agentscope_ollama_model import BurryOllamaChatModel

        ensure_agentscope_initialized()
        agent = BrowserAgent(
            name="burry-browser",
            model=BurryOllamaChatModel(
                model_name="gemma4:e4b",
                stream=False,
                options={"num_ctx": 4096},
            ),
            formatter=OllamaChatFormatter(max_tokens=512),
        )
        loop = _get_persistent_loop()
        future = asyncio.run_coroutine_threadsafe(
            agent(Msg("user", task, "user")),
            loop,
        )
        result = future.result(timeout=30)
        return result.get_text_content() if hasattr(result, "get_text_content") else str(result)
    except (ImportError, Exception):
        pass
    return _sync_browse_custom(task)
