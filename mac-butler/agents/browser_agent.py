#!/usr/bin/env python3
"""AgentScope-style browser-use agent — autonomous web navigation.
Uses Playwright to browse and extract information from any website.
Falls back to BrowsingAgent if Playwright unavailable.
"""
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


async def browse_and_act(task: str, model_name: str = "gemma4:e4b") -> str:
    """Give Burry a browser task in plain English. It figures out how to do it.

    Examples:
    - 'Go to github.com/Aadi262/Burry and tell me the latest commit message'
    - 'Search Hacker News for AI agents and summarize the top 3 posts'
    - 'Open mail.google.com and tell me how many unread emails I have'
    """
    try:
        from playwright.async_api import async_playwright
        from brain.ollama_client import _call

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Navigate if URL is in the task
            target_url = _extract_task_url(task)
            if target_url:
                await page.goto(target_url, wait_until="networkidle", timeout=10000)
            elif any(kw in task.lower() for kw in ["github", "hackernews", "hn ", "reddit", "mail.google"]):
                # Derive simple URL from task
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
        # Fallback to existing BrowsingAgent
        try:
            from browser.agent import BrowsingAgent
            result = BrowsingAgent().search(task, question=task)
            return result.get("result", f"Browser error: {exc}")
        except Exception:
            return f"Browser unavailable: {exc}"


def sync_browse(task: str) -> str:
    """Synchronous wrapper for use in tool calls."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(browse_and_act(task))
    finally:
        loop.close()
