#!/usr/bin/env python3
"""Burry Tools Registry — all tools as decorated functions.
Import this module once to register everything into the Toolkit.
"""
from __future__ import annotations

import subprocess

from brain.toolkit import tool
from executor.engine import Executor

_executor = Executor()


@tool
def open_project(name: str) -> str:
    """Open a named project in the editor."""
    result = _executor.run([{"type": "open_project", "name": name}])
    return result[0].get("result", "opened") if result else "opened"


@tool
def focus_app(app: str) -> str:
    """Focus or open a macOS application by name."""
    result = _executor.run([{"type": "focus_app", "app": app}])
    return result[0].get("result", "focused") if result else "focused"


@tool
def minimize_app(app: str) -> str:
    """Minimize a macOS application window."""
    result = _executor.run([{"type": "minimize_app", "app": app}])
    return result[0].get("result", "minimized") if result else "minimized"


@tool
def hide_app(app: str) -> str:
    """Hide a macOS application without quitting it."""
    result = _executor.run([{"type": "hide_app", "app": app}])
    return result[0].get("result", "hidden") if result else "hidden"


@tool
def run_shell(command: str, project: str = "") -> str:
    """Run a shell command in a project directory."""
    result = _executor.run([{"type": "run_shell", "command": command, "project": project}])
    return result[0].get("result", "") if result else ""


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Open Gmail compose with recipient, subject and body pre-filled."""
    result = _executor.run([{"type": "send_email", "to": to, "subject": subject, "body": body}])
    return result[0].get("result", "email opened") if result else "email opened"


@tool
def send_whatsapp(contact: str, message: str) -> str:
    """Send a WhatsApp message to a contact via keyboard simulation."""
    result = _executor.run([{"type": "send_whatsapp", "contact": contact, "message": message}])
    return result[0].get("result", "sent") if result else "sent"


@tool
def chrome_open_tab(url: str) -> str:
    """Open a URL in a new Chrome tab."""
    result = _executor.run([{"type": "chrome_open_tab", "url": url}])
    return result[0].get("result", "opened") if result else "opened"


@tool
def chrome_focus_tab(tab_title: str) -> str:
    """Switch to a Chrome tab by its title."""
    result = _executor.run([{"type": "chrome_focus_tab", "tab_title": tab_title}])
    return result[0].get("result", "focused") if result else "focused"


@tool
def chrome_close_tab(tab_title: str) -> str:
    """Close a Chrome tab by its title."""
    result = _executor.run([{"type": "chrome_close_tab", "tab_title": tab_title}])
    return result[0].get("result", "closed") if result else "closed"


@tool
def spotify_control(action: str, query: str = "") -> str:
    """Control Spotify: play, pause, next, prev, volume_up, volume_down, now_playing."""
    action_type = "play_music" if action == "play" else f"spotify_{action}"
    result = _executor.run([{"type": action_type, "query": query}])
    return result[0].get("result", action) if result else action


@tool
def git_commit(project: str = "", message_hint: str = "") -> str:
    """Generate a commit message from staged changes, confirm, and commit."""
    result = _executor.run([{"type": "git_commit", "project": project, "message_hint": message_hint}])
    return result[0].get("result", "committed") if result else "committed"


@tool
def set_reminder(time: str, message: str) -> str:
    """Create a macOS reminder at a time offset like '30 minutes' or '2 hours'."""
    result = _executor.run([{"type": "remind_in", "time": time, "message": message}])
    return result[0].get("result", "reminder set") if result else "reminder set"


@tool
def ssh_vps(command: str) -> str:
    """Run a shell command on the configured VPS over SSH."""
    result = _executor.run([{"type": "ssh_command", "cmd": command}])
    return result[0].get("result", "") if result else ""


@tool
def obsidian_note(title: str, content: str) -> str:
    """Create or append to an Obsidian note."""
    result = _executor.run([{"type": "obsidian_note", "title": title, "content": content, "folder": "Daily"}])
    return result[0].get("result", "noted") if result else "noted"


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
    summary = _call(f"Summarize in under 20 words: {raw}", "gemma4:e4b", max_tokens=40, temperature=0.1)
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
