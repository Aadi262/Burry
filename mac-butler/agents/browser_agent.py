#!/usr/bin/env python3
"""AgentScope-style browser-use agent — autonomous web navigation.
Uses Playwright to browse and extract information from any website.
Falls back to BrowsingAgent if Playwright unavailable.
"""
from __future__ import annotations

import asyncio
import re


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
            url_match = re.search(r'https?://\S+', task)
            if url_match:
                await page.goto(url_match.group(0), wait_until="networkidle", timeout=10000)
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
