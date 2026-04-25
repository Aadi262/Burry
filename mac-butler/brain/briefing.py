#!/usr/bin/env python3
"""Startup briefing helpers for trigger-time voice sessions."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, wait

import requests


def _github_line() -> str:
    try:
        response = requests.get("https://api.github.com/users/Aadi262/events?per_page=10", timeout=3)
        events = response.json() if response.content else []
    except Exception:
        return ""
    pushes = [event for event in events if isinstance(event, dict) and event.get("type") == "PushEvent"]
    if not pushes:
        return ""
    latest = pushes[0]
    repo = str(((latest.get("repo") or {}).get("name", ""))).split("/")[-1]
    commits = list(((latest.get("payload") or {}).get("commits") or []))
    message = str((commits[0] or {}).get("message", "") if commits else "").strip()[:40]
    if not repo and not message:
        return ""
    return f"Last push: {repo or 'unknown'} - {message}".strip(" -")


def _weather_line() -> str:
    try:
        response = requests.get(
            "https://wttr.in/Mumbai",
            params={"format": "%l: %t %C"},
            timeout=3,
        )
        response.encoding = response.encoding or "utf-8"
        return " ".join(str(response.text or "").split()).strip()
    except Exception:
        return ""


def _task_line() -> str:
    try:
        from tasks.task_store import get_active_tasks
    except Exception:
        return ""
    tasks = get_active_tasks()[:2]
    if not tasks:
        return ""
    titles = [str(task.get("title", "")).strip()[:25] for task in tasks if str(task.get("title", "")).strip()]
    return "Pending: " + ", ".join(titles) if titles else ""


def _calendar_line() -> str:
    script = '''
tell application "Calendar"
  set today to current date
  set todayEnd to today + 1 * days
  set eventList to {}
  repeat with c in calendars
    repeat with e in (events of c whose start date >= today and start date < todayEnd)
      set end of eventList to summary of e
    end repeat
  end repeat
  return eventList
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return ""
    output = str(result.stdout or "").strip()
    return f"Calendar: {output[:50]}" if output else ""


def build_briefing() -> str:
    jobs = [
        ("github", _github_line),
        ("weather", _weather_line),
        ("tasks", _task_line),
        ("calendar", _calendar_line),
    ]
    results = {name: "" for name, _fn in jobs}

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        future_map = {executor.submit(fn): name for name, fn in jobs}
        done, not_done = wait(future_map, timeout=5)
        for future in not_done:
            future.cancel()
        for future in done:
            name = future_map[future]
            try:
                results[name] = str(future.result() or "").strip()
            except Exception:
                results[name] = ""

    parts = [results["github"], results["weather"], results["tasks"], results["calendar"]]
    spoken = [part for part in parts if part][:3]
    if not spoken:
        return "You're up. What are we building?"
    return ". ".join(spoken) + ". What are we building?"
