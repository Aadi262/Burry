#!/usr/bin/env python3
"""Burry Tools Registry — all tools as decorated functions.
Import this module once to register everything into the Toolkit.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from butler_config import TOOL_SUMMARIZER_MODEL, VPS_HOSTS
from brain.toolkit import get_toolkit, tool
from executor.engine import Executor

_executor = Executor()


def _run_tool_action(action: dict, fallback: str) -> str:
    results = _executor.run([action])
    if not results:
        return fallback
    first = results[0] if isinstance(results[0], dict) else {}
    verification_detail = " ".join(str(first.get("verification_detail", "") or "").split()).strip()
    if verification_detail:
        return verification_detail
    text = " ".join(str(first.get("result", "") or first.get("error", "") or "").split()).strip()
    return text or fallback


def _project_cwd(project: str) -> str | None:
    name = " ".join(str(project or "").split()).strip()
    if not name:
        return None
    try:
        from projects import get_project

        item = get_project(name, hydrate_blurb=True)
    except Exception:
        item = None
    path = str((item or {}).get("path", "")).strip()
    return path or None


def _minutes_from_time_spec(value: str) -> int:
    text = " ".join(str(value or "").lower().split()).strip()
    if not text:
        return 30
    digits = "".join(ch for ch in text if ch.isdigit())
    amount = int(digits) if digits else 30
    if "day" in text:
        return max(amount, 1) * 24 * 60
    if "hour" in text or text.endswith("hr") or text.endswith("hrs"):
        return max(amount, 1) * 60
    return max(amount, 1)


def _default_vps_host() -> str:
    if VPS_HOSTS:
        return str(VPS_HOSTS[0].get("host", "")).strip()
    return ""


@tool
def open_project(name: str) -> str:
    """Open a named project in the editor."""
    return _run_tool_action({"type": "open_project", "name": name}, "opened")


@tool
def focus_app(app: str) -> str:
    """Focus or open a macOS application by name."""
    return _run_tool_action({"type": "focus_app", "app": app}, "focused")


@tool
def minimize_app(app: str) -> str:
    """Minimize a macOS application window."""
    return _run_tool_action({"type": "minimize_app", "app": app}, "minimized")


@tool
def hide_app(app: str) -> str:
    """Hide a macOS application without quitting it."""
    return _run_tool_action({"type": "hide_app", "app": app}, "hidden")


@tool
def run_shell(command: str, project: str = "") -> str:
    """Run a shell command in a project directory."""
    return _run_tool_action({"type": "run_command", "cmd": command, "cwd": _project_cwd(project)}, "")


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Open Gmail compose with recipient, subject and body pre-filled."""
    return _run_tool_action({"type": "send_email", "to": to, "subject": subject, "body": body}, "email opened")


@tool
def send_whatsapp(contact: str, message: str) -> str:
    """Send a WhatsApp message to a contact via keyboard simulation."""
    return _run_tool_action({"type": "send_whatsapp", "contact": contact, "message": message}, "sent")


@tool
def chrome_open_tab(url: str) -> str:
    """Open a URL in a new Chrome tab."""
    return _run_tool_action({"type": "chrome_open_tab", "url": url}, "opened")


@tool
def chrome_focus_tab(tab_title: str) -> str:
    """Switch to a Chrome tab by its title."""
    return _run_tool_action({"type": "chrome_focus_tab", "tab_title": tab_title}, "focused")


@tool
def chrome_close_tab(tab_title: str) -> str:
    """Close a Chrome tab by its title."""
    return _run_tool_action({"type": "chrome_close_tab", "tab_title": tab_title}, "closed")


@tool
def spotify_control(action: str, query: str = "") -> str:
    """Control Spotify: play, pause, next, prev, volume_up, volume_down, now_playing."""
    action_type = "play_music" if action == "play" else f"spotify_{action}"
    return _run_tool_action({"type": action_type, "query": query}, action)


@tool
def git_commit(project: str = "", message_hint: str = "") -> str:
    """Generate a commit message from staged changes, confirm, and commit."""
    cwd = _project_cwd(project) or "~/Burry/mac-butler"
    expanded_cwd = str(Path(cwd).expanduser())
    diff = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=expanded_cwd,
        capture_output=True,
        text=True,
        timeout=20,
    )
    staged_diff = str(diff.stdout or "").strip()
    if not staged_diff:
        return "No staged changes to commit"
    message = " ".join(str(message_hint or "").split()).strip() or "Update staged changes"
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=expanded_cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return " ".join((commit.stdout or commit.stderr or message).split()).strip() or message


@tool
def set_reminder(time: str, message: str) -> str:
    """Create a macOS reminder at a time offset like '30 minutes' or '2 hours'."""
    return _run_tool_action({"type": "remind_in", "minutes": _minutes_from_time_spec(time), "message": message}, "reminder set")


@tool
def ssh_vps(command: str) -> str:
    """Run a shell command on the configured VPS over SSH."""
    return _run_tool_action({"type": "ssh_command", "host": _default_vps_host(), "cmd": command}, "")


@tool
def obsidian_note(title: str, content: str) -> str:
    """Create or append to an Obsidian note."""
    return _run_tool_action({"type": "obsidian_note", "title": title, "content": content, "folder": "Daily"}, "noted")


@tool
def take_screenshot_and_describe(question: str = "") -> str:
    """Take a screenshot and describe what is on screen."""
    from agents.vision import describe_screen
    return describe_screen(question)


@tool
def recall_memory(query: str, project: str = "") -> str:
    """Search past sessions and memory for relevant context."""
    from memory.store import semantic_search
    results = semantic_search(query, n=3)
    return "\n".join(r.get("speech", "") for r in results)


@tool
def browse_web(query: str, url: str = "") -> str:
    """Search the web or fetch and summarize a URL."""
    from browser.agent import BrowsingAgent
    agent = BrowsingAgent()
    if url:
        return agent.fetch(url, question=query)
    result = agent.search(query, question=query)
    return result.get("result", "")


@tool
def volume_up() -> str:
    """Turn up the Mac system volume."""
    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 10)"])
    return "volume up"


@tool
def volume_down() -> str:
    """Turn down the Mac system volume."""
    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 10)"])
    return "volume down"


@tool
def volume_mute() -> str:
    """Mute or unmute the Mac system volume."""
    subprocess.run(["osascript", "-e", "set volume with output muted"])
    return "muted"


@tool
def lock_screen() -> str:
    """Lock the Mac screen immediately."""
    subprocess.run(["pmset", "displaysleepnow"])
    return "screen locked"


@tool
def clipboard_read() -> str:
    """Read the current clipboard contents."""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout.strip()


@tool
def clipboard_write(text: str) -> str:
    """Write text to the clipboard."""
    subprocess.run(["pbcopy"], input=text.encode())
    return "copied"


@tool
def send_imessage(contact: str, message: str) -> str:
    """Send an iMessage to a contact via Messages.app."""
    script = f'tell application "Messages" to send "{message}" to buddy "{contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)
    return f"iMessage sent to {contact}"


@tool
def dark_mode_toggle() -> str:
    """Toggle macOS between dark and light mode."""
    script = 'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'
    subprocess.run(["osascript", "-e", script])
    return "toggled"


@tool
def web_search_summarize(query: str) -> str:
    """Search the web and return a short spoken summary."""
    from browser.agent import BrowsingAgent
    from brain.ollama_client import _call
    result = BrowsingAgent().search(query, question=query)
    raw = result.get("result", "")
    if not raw:
        return "I couldn't find anything."
    summary = _call(
        f"Summarize in under 20 words: {raw}",
        TOOL_SUMMARIZER_MODEL,
        max_tokens=40,
        temperature=0.1,
        timeout_hint="voice",
    )
    return summary or raw[:200]


@tool
def browse_and_act(task: str) -> str:
    """Autonomously browse the web to complete a task.
    Can navigate, click, fill forms, and extract information from any website."""
    from agents.browser_agent import sync_browse
    return sync_browse(task)


@tool
def deep_research(question: str) -> str:
    """Research a complex question by searching multiple sources and synthesizing the answer.
    Best for: latest developments in X, compare A and B, explain the current state of Y."""
    from agents.research_agent import deep_research as _research
    return _research(question)


@tool
def plan_and_execute(task: str) -> str:
    """Plan and execute a complex multi-step task automatically.
    Use when the request requires multiple actions in sequence."""
    from agents.planner_agent import plan_and_execute as _plan
    return _plan(task, {})


@tool
def search_knowledge_base(query: str) -> str:
    """Search your indexed local documents and notes for relevant information.
    Use for: what does the spec say about X, find my notes on Y, look up Z in my docs."""
    from memory.knowledge_base import search_knowledge_base as _search
    results = _search(query)
    if not results:
        return "Nothing found in knowledge base."
    return "\n\n".join(f"[{r['title']}]: {r['text'][:300]}" for r in results)


@tool
def index_file(file_path: str, title: str = "") -> str:
    """Add a file to Burry's searchable knowledge base."""
    from memory.knowledge_base import index_file as _index
    count = _index(file_path, title)
    return f"Indexed {count} chunks from {file_path}"


def get_tools_schema() -> list[dict]:
    return get_toolkit().get_tools()


TOOLS = get_tools_schema()
