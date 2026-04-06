#!/usr/bin/env python3
"""
daemon/heartbeat.py
KAIROS-style background heartbeat for quiet proactive nudges.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime

from butler_config import (
    HEARTBEAT_ENABLED,
    HEARTBEAT_INTERVAL_MINUTES,
    HEARTBEAT_MODEL,
    OLLAMA_MODEL,
)
from brain.ollama_client import _call, _strip
from context import build_structured_context
from executor.engine import Executor

SAFE_ACTIONS = {"notify", "remind_in", "obsidian_note"}


def _upcoming_calendar_lines(limit: int = 2) -> list[str]:
    script = """
tell application "Calendar"
    set nowDate to current date
    set futureDate to nowDate + (7 * days)
    set eventLines to {}
    repeat with cal in calendars
        repeat with ev in (every event of cal whose start date is greater than or equal to nowDate and start date is less than or equal to futureDate)
            set end of eventLines to ((summary of ev as text) & "||" & ((start date of ev) as string))
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to linefeed
return eventLines as text
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []

    raw = str(result.stdout or "").strip()
    if not raw:
        return []

    lines = []
    for line in raw.splitlines():
        title, _, start_text = line.partition("||")
        title = " ".join(title.split()).strip()
        start_text = " ".join(start_text.split()).strip()
        if not title:
            continue
        if start_text:
            lines.append(f"Upcoming: {title} at {start_text}")
        else:
            lines.append(f"Upcoming: {title}")
        if len(lines) >= max(1, limit):
            break
    return lines


def _safe_action_from_response(data: dict) -> dict | None:
    action = data.get("action")
    if isinstance(action, dict) and action.get("type") in SAFE_ACTIONS:
        return action
    if data.get("notify") and data.get("message"):
        return {
            "type": "notify",
            "title": "Burry",
            "message": str(data["message"])[:120],
        }
    return None


def heartbeat_tick() -> None:
    """Run one heartbeat evaluation."""
    try:
        hour = datetime.now().hour
        if 5 <= hour <= 9:
            return

        ctx = build_structured_context()
        calendar_lines = _upcoming_calendar_lines(limit=2)
        calendar_block = ""
        if calendar_lines:
            calendar_block = "\n[CALENDAR]\n" + "\n".join(calendar_lines)
        prompt = f"""You are a quiet background monitor for Aditya's work.
Given the current context, decide if there is exactly one useful low-risk thing to surface.

Context:
{ctx['formatted'][:500]}{calendar_block}

Rules:
- Stay silent unless something is genuinely worth interrupting for
- Only use a safe action: notify, remind_in, or obsidian_note
- Keep any notification message under 20 words

Output ONLY JSON or the word "nothing".
Examples:
{{"action": {{"type": "notify", "title": "Burry", "message": "Contabo VPS looks unreachable"}}}}
{{"action": {{"type": "remind_in", "minutes": 30, "message": "Check the deploy again"}}}}
nothing"""

        raw = _call(prompt, HEARTBEAT_MODEL or OLLAMA_MODEL, temperature=0.2, max_tokens=120)
        if raw.lower().strip().startswith("nothing"):
            return

        try:
            data = json.loads(_strip(raw))
        except Exception:
            return

        action = _safe_action_from_response(data)
        if not action:
            return

        result = Executor().run([action])
        print(
            f"[Heartbeat] {datetime.now().strftime('%H:%M')} "
            f"{action.get('type')}: {result[0].get('result', '')}"
        )
    except Exception as exc:
        print(f"[Heartbeat] Error: {exc}")


def run_heartbeat() -> None:
    interval_seconds = max(1, HEARTBEAT_INTERVAL_MINUTES) * 60
    print(f"[Heartbeat] Started - checking every {interval_seconds // 60} minutes")
    if not HEARTBEAT_ENABLED:
        print("[Heartbeat] Warning: HEARTBEAT_ENABLED is False in butler_config.py")
    while True:
        time.sleep(interval_seconds)
        heartbeat_tick()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Butler Heartbeat")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously instead of a single test tick",
    )
    args = parser.parse_args()

    if args.loop:
        run_heartbeat()
    else:
        print("[Heartbeat] Single tick test...")
        heartbeat_tick()
        print("[Heartbeat] Done")
