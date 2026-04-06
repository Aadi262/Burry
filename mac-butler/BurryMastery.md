You are a senior engineer doing a complete architectural upgrade of Burry OS — a local AI voice operator for macOS. Read the entire codebase first: git log --oneline -20, then read butler.py, agents/runner.py, executor/engine.py, brain/ollama_client.py, intents/router.py, memory/store.py, memory/learner.py, projects/dashboard.py. Understand every component before touching anything.
Then implement all of the following. This is a full sprint. Commit each numbered section separately. Run the full test suite before each commit. Do not stop between items.
INSTALL DEPENDENCIES FIRST:
bashcd ~/Burry/mac-butler
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/pip install agentscope httpx fastapi uvicorn opentelemetry-sdk opentelemetry-exporter-otlp
STEAL 1 — TOOLKIT: Replace the 200-line if/elif _dispatch() in executor/engine.py with AgentScope Toolkit.
Create mac-butler/brain/toolkit.py:
python#!/usr/bin/env python3
"""AgentScope Toolkit — single source of truth for all Burry tools.
Adding a new tool = one decorated function. Zero other file changes.
"""
from agentscope.tool import Toolkit

_toolkit = Toolkit()

def get_toolkit() -> Toolkit:
    return _toolkit

def tool(func):
    """Decorator that registers a function as a Burry tool."""
    _toolkit.add(func)
    return func
Create mac-butler/brain/tools_registry.py — move every tool here as a decorated function:
pythonfrom brain.toolkit import tool
from executor.engine import Executor

_executor = Executor()

@tool
def open_project(name: str) -> str:
    """Open a named project in the editor."""
    result = _executor.run([{"type": "open_project", "name": name}])
    return result[0].get("result", "opened")

@tool
def focus_app(app: str) -> str:
    """Focus or open a macOS application by name."""
    result = _executor.run([{"type": "focus_app", "app": app}])
    return result[0].get("result", "focused")

@tool
def minimize_app(app: str) -> str:
    """Minimize a macOS application window."""
    result = _executor.run([{"type": "minimize_app", "app": app}])
    return result[0].get("result", "minimized")

@tool
def run_shell(command: str, project: str = "") -> str:
    """Run a shell command in a project directory."""
    result = _executor.run([{"type": "run_shell", "command": command, "project": project}])
    return result[0].get("result", "")

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Open Gmail compose with recipient, subject and body pre-filled."""
    result = _executor.run([{"type": "send_email", "to": to, "subject": subject, "body": body}])
    return result[0].get("result", "email opened")

@tool
def send_whatsapp(contact: str, message: str) -> str:
    """Send a WhatsApp message to a contact via keyboard simulation."""
    result = _executor.run([{"type": "send_whatsapp", "contact": contact, "message": message}])
    return result[0].get("result", "sent")

@tool
def chrome_open_tab(url: str) -> str:
    """Open a URL in a new Chrome tab."""
    result = _executor.run([{"type": "chrome_open_tab", "url": url}])
    return result[0].get("result", "opened")

@tool
def chrome_focus_tab(tab_title: str) -> str:
    """Switch to a Chrome tab by its title."""
    result = _executor.run([{"type": "chrome_focus_tab", "tab_title": tab_title}])
    return result[0].get("result", "focused")

@tool
def chrome_close_tab(tab_title: str) -> str:
    """Close a Chrome tab by its title."""
    result = _executor.run([{"type": "chrome_close_tab", "tab_title": tab_title}])
    return result[0].get("result", "closed")

@tool
def spotify_control(action: str, query: str = "") -> str:
    """Control Spotify: play, pause, next, prev, volume_up, volume_down, now_playing."""
    result = _executor.run([{"type": "spotify_" + action if action != "play" else "play_music", "query": query}])
    return result[0].get("result", action)

@tool
def git_commit(project: str = "", message_hint: str = "") -> str:
    """Generate a commit message from staged changes, confirm, and commit."""
    result = _executor.run([{"type": "git_commit", "project": project, "message_hint": message_hint}])
    return result[0].get("result", "committed")

@tool
def set_reminder(time: str, message: str) -> str:
    """Create a macOS reminder at a time offset like '30 minutes' or '2 hours'."""
    result = _executor.run([{"type": "remind_in", "time": time, "message": message}])
    return result[0].get("result", "reminder set")

@tool
def ssh_vps(command: str) -> str:
    """Run a shell command on the configured VPS over SSH."""
    result = _executor.run([{"type": "ssh_command", "cmd": command}])
    return result[0].get("result", "")

@tool
def obsidian_note(title: str, content: str) -> str:
    """Create or append to an Obsidian note."""
    result = _executor.run([{"type": "obsidian_note", "title": title, "content": content, "folder": "Daily"}])
    return result[0].get("result", "noted")

@tool
def take_screenshot_and_describe(question: str = "") -> str:
    """Take a screenshot and describe what is on screen."""
    from agents.vision import describe_screen
    return describe_screen(question)

@tool
def recall_memory(query: str, project: str = "") -> str:
    """Search past sessions and memory for relevant context."""
    from memory.store import semantic_search
    results = semantic_search(query, top_k=3)
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
    import subprocess
    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 10)"])
    return "volume up"

@tool
def volume_down() -> str:
    """Turn down the Mac system volume."""
    import subprocess
    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 10)"])
    return "volume down"

@tool
def volume_mute() -> str:
    """Mute or unmute the Mac system volume."""
    import subprocess
    subprocess.run(["osascript", "-e", "set volume with output muted"])
    return "muted"

@tool
def lock_screen() -> str:
    """Lock the Mac screen immediately."""
    import subprocess
    subprocess.run(["pmset", "displaysleepnow"])
    return "screen locked"

@tool
def clipboard_read() -> str:
    """Read the current clipboard contents."""
    import subprocess
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout.strip()

@tool
def clipboard_write(text: str) -> str:
    """Write text to the clipboard."""
    import subprocess
    subprocess.run(["pbcopy"], input=text.encode())
    return "copied"

@tool
def send_imessage(contact: str, message: str) -> str:
    """Send an iMessage to a contact via Messages.app."""
    import subprocess
    script = f'tell application "Messages" to send "{message}" to buddy "{contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)
    return f"iMessage sent to {contact}"

@tool
def dark_mode_toggle() -> str:
    """Toggle macOS between dark and light mode."""
    import subprocess
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
In brain/tools.py replace TOOLS list with:
pythonfrom brain.toolkit import get_toolkit
import brain.tools_registry  # noqa — triggers all @tool decorations

def get_tools_schema():
    return get_toolkit().get_tools()

TOOLS = get_tools_schema()
In butler.py find _execute_tool_call(). Replace entire function with:
pythondef _execute_tool_call(tool_name: str, arguments: dict, ctx: dict, user_text: str = "") -> dict:
    from brain.toolkit import get_toolkit
    import brain.tools_registry  # noqa
    toolkit = get_toolkit()
    note_tool_started(tool_name, str(arguments))
    try:
        result = toolkit.call(tool_name, **arguments)
        note_tool_finished(tool_name, "ok", str(result)[:200])
        return {"tool": tool_name, "actions": [{"type": tool_name}], "results": [{"action": tool_name, "status": "ok", "result": str(result)}], "speech": str(result)}
    except Exception as exc:
        note_tool_finished(tool_name, "error", str(exc))
        return {"tool": tool_name, "actions": [], "results": [{"action": tool_name, "status": "error", "error": str(exc)}], "speech": f"I had trouble with {tool_name}."}
Commit: Replace executor dispatch with AgentScope Toolkit
STEAL 2 — MSGHUB: Replace agents/runner.py with AgentScope parallel fan-out.
Rewrite agents/runner.py entirely:
python#!/usr/bin/env python3
"""AgentScope MsgHub-based agent runner.
Replaces the custom threaded fan-out with proper parallel pipelines.
"""
import asyncio
from typing import Any
import agentscope
from agentscope.agent import ReActAgent
from agentscope.message import Msg
from agentscope.pipeline import MsgHub, fanout_pipeline
from agentscope.model import OllamaChatModel
from butler_config import BUTLER_MODELS
from runtime.telemetry import note_agent_result
from runtime.notify import notify

_INITIALIZED = False

def _ensure_init():
    global _INITIALIZED
    if _INITIALIZED:
        return
    agentscope.init(
        model_configs=[{
            "config_name": "burry_fast",
            "model_type": "ollama_chat",
            "model_name": BUTLER_MODELS.get("agents", "gemma4:e4b"),
            "api_url": "http://localhost:11434/api/chat",
            "stream": False,
        }]
    )
    _INITIALIZED = True

def _make_agent(name: str, prompt: str) -> ReActAgent:
    _ensure_init()
    return ReActAgent(
        name=name,
        sys_prompt=prompt,
        model_config_name="burry_fast",
    )

AGENT_REGISTRY = {
    "search": "You search the web and return a concise factual summary under 30 words.",
    "reddit": "You fetch top Reddit discussions and summarize the key points briefly.",
    "hn": "You fetch Hacker News top stories and summarize the most relevant one.",
    "news": "You fetch latest tech news and summarize the top story in under 25 words.",
    "vps": "You check VPS server status and report CPU, memory, and disk usage.",
}

async def _run_agent_async(name: str, query: str) -> dict:
    try:
        agent = _make_agent(name, AGENT_REGISTRY.get(name, "You are a helpful assistant."))
        msg = Msg("user", query, "user")
        result = await agent(msg)
        text = result.get_text_content() if hasattr(result, "get_text_content") else str(result)
        note_agent_result(name, "ok", text[:300])
        notify("Burry", f"{name} agent done", subtitle=text[:60])
        return {"agent": name, "status": "ok", "result": text}
    except Exception as exc:
        note_agent_result(name, "error", str(exc))
        return {"agent": name, "status": "error", "result": ""}

async def run_agents_parallel(query: str, agent_names: list[str]) -> list[dict]:
    """Run multiple agents in parallel via AgentScope fanout. Non-blocking."""
    tasks = [_run_agent_async(name, query) for name in agent_names]
    return await asyncio.gather(*tasks, return_exceptions=False)

def run_background_agents(query: str, agent_names: list[str]) -> None:
    """Fire and forget — runs agents in background thread without blocking voice pipeline."""
    import threading
    def _bg():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_agents_parallel(query, agent_names))
        finally:
            loop.close()
    threading.Thread(target=_bg, daemon=True, name=f"burry-agents-{query[:20]}").start()
In butler.py find every call to the old run_agent_async() and replace with run_background_agents() from the new runner. Commit: Replace agent runner with AgentScope MsgHub parallel pipeline
STEAL 3 — STREAMING TTS: Make Burry speak as tokens arrive instead of waiting for full response.
In brain/ollama_client.py add a streaming call function:
pythonimport httpx

async def stream_llm_tokens(prompt: str, model: str, system: str = "") -> AsyncIterator[str]:
    """Stream tokens from Ollama as they arrive. Yields sentence chunks for TTS."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": True,
    }
    buffer = ""
    async with httpx.AsyncClient(timeout=30) as client:
        async with client.stream("POST", "http://localhost:11434/api/generate", json=payload) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    buffer += token
                    # Yield complete sentences for TTS
                    while any(p in buffer for p in [".", "!", "?"]):
                        for punct in [".", "!", "?"]:
                            if punct in buffer:
                                idx = buffer.index(punct) + 1
                                sentence = buffer[:idx].strip()
                                buffer = buffer[idx:].strip()
                                if sentence:
                                    yield sentence
                                break
                    if chunk.get("done"):
                        if buffer.strip():
                            yield buffer.strip()
                        break
                except Exception:
                    continue
In butler.py find _speak_or_print() and the main LLM call path. Add a streaming variant:
pythonasync def _stream_response_with_tts(prompt: str, ctx: dict) -> str:
    """Stream LLM response and speak each sentence as it arrives. 
    User hears first words within 1-2 seconds instead of waiting 45s."""
    from brain.ollama_client import stream_llm_tokens
    from voice import speak
    import asyncio
    
    full_response = ""
    model = BUTLER_MODELS.get("voice", "gemma4:e4b")
    
    async for sentence in stream_llm_tokens(prompt, model):
        full_response += " " + sentence
        # Speak each sentence immediately without waiting for the rest
        threading.Thread(target=speak, args=(sentence,), daemon=True).start()
    
    return full_response.strip()
Wire this into the voice response path. When Butler has a response ready, instead of calling speak(full_response), call asyncio.run(_stream_response_with_tts(prompt, ctx)). The user hears the first sentence in 1-2 seconds. Commit: Add streaming TTS — speak as tokens arrive
STEAL 4 — SKILLS AUTO-LOADER: Replace hardcoded router.py intents with auto-loading skills directory.
Create mac-butler/skills/init.py:
python"""Skills auto-loader — drop a .py file in this directory to add a new Burry skill.
Each skill file must export:
  TRIGGER_PATTERNS: list[str]  — regex patterns that activate this skill
  DESCRIPTION: str             — one sentence what this skill does
  execute(text: str, entities: dict) -> dict  — returns {"speech": str, "actions": list}
"""
import importlib
import re
from pathlib import Path
from typing import Callable

_REGISTRY: list[dict] = []

def load_skills() -> None:
    """Scan skills/ directory and register all skills automatically."""
    skills_dir = Path(__file__).parent
    for skill_file in skills_dir.glob("*.py"):
        if skill_file.stem.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"skills.{skill_file.stem}")
            patterns = getattr(module, "TRIGGER_PATTERNS", [])
            description = getattr(module, "DESCRIPTION", skill_file.stem)
            execute_fn = getattr(module, "execute", None)
            if patterns and execute_fn:
                _REGISTRY.append({
                    "name": skill_file.stem,
                    "patterns": [re.compile(p, re.IGNORECASE) for p in patterns],
                    "description": description,
                    "execute": execute_fn,
                })
                print(f"[Skills] Loaded: {skill_file.stem} ({len(patterns)} patterns)")
        except Exception as exc:
            print(f"[Skills] Failed to load {skill_file.stem}: {exc}")

def match_skill(text: str) -> tuple[dict | None, dict]:
    """Return (skill, entities) if text matches any skill pattern."""
    for skill in _REGISTRY:
        for pattern in skill["patterns"]:
            match = pattern.search(text)
            if match:
                return skill, match.groupdict()
    return None, {}

def list_skills() -> list[str]:
    return [f"{s['name']}: {s['description']}" for s in _REGISTRY]
Create mac-butler/skills/email_skill.py:
pythonDESCRIPTION = "Send emails via Gmail with subject and body"
TRIGGER_PATTERNS = [
    r"email (?P<recipient>\S+@\S+) (?:with subject|subject) (?P<subject>.+?)(?:\s+(?:body|message|saying|boyd)\s+(?P<body>.+))?$",
    r"send (?:an? )?email to (?P<recipient>\S+@\S+)",
    r"compose (?:an? )?(?:email|mail) to (?P<recipient>\S+)",
]

def execute(text: str, entities: dict) -> dict:
    recipient = entities.get("recipient", "").strip().rstrip("with,. ")
    subject = entities.get("subject", "").strip()
    body = entities.get("body", "").strip()
    import urllib.parse
    params = {"view": "cm", "fs": "1", "tf": "1", "to": recipient}
    if subject:
        params["su"] = subject
    if body:
        params["body"] = body
    url = "https://mail.google.com/mail/u/0/?" + urllib.parse.urlencode(params)
    import subprocess
    subprocess.run(["open", url])
    return {"speech": f"Opening Gmail to {recipient}.", "actions": [{"type": "open_url", "url": url}]}
Create mac-butler/skills/calendar_skill.py:
pythonDESCRIPTION = "Read and create macOS Calendar events"
TRIGGER_PATTERNS = [
    r"what(?:'s| is) (?:on )?my (?:calendar|schedule|agenda)(?: today| tomorrow)?",
    r"do I have (?:any )?(?:meetings?|events?) (?:today|tomorrow)?",
    r"create (?:a )?(?:meeting|event|appointment) (?:called|named|titled)? ?(?P<title>.+?) (?:at|on) (?P<time>.+)",
]

def execute(text: str, entities: dict) -> dict:
    import subprocess
    script = '''
    tell application "Calendar"
        set today to current date
        set todayEvents to every event of every calendar whose start date is greater than today and start date is less than (today + 1 * days)
        set eventList to ""
        repeat with evt in todayEvents
            set eventList to eventList & summary of evt & " at " & (start date of evt as string) & "\n"
        end repeat
        return eventList
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    events = result.stdout.strip()
    if events:
        return {"speech": f"Today you have: {events[:200]}", "actions": []}
    return {"speech": "You have no events today.", "actions": []}
Create mac-butler/skills/imessage_skill.py:
pythonDESCRIPTION = "Send iMessages via Messages.app"
TRIGGER_PATTERNS = [
    r"(?:i?message|text) (?P<contact>.+?) (?:that |saying |to say )?(?P<message>.+)",
    r"send (?P<contact>.+?) (?:an? )?(?:i?message|text)(?: saying)? (?P<message>.+)",
]

def execute(text: str, entities: dict) -> dict:
    contact = entities.get("contact", "").strip()
    message = entities.get("message", "").strip()
    import subprocess
    script = f'tell application "Messages" to send "{message}" to buddy "{contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)
    return {"speech": f"iMessage sent to {contact}.", "actions": [{"type": "imessage", "contact": contact}]}
Wire skills into butler.py — at the very top of handle_input(), before routing:
pythonfrom skills import match_skill, load_skills, list_skills

# Call once at startup
load_skills()

def handle_input(text: str, ...):
    # Check skills FIRST before intent router
    skill, entities = match_skill(text)
    if skill:
        result = skill["execute"](text, entities)
        _speak_or_print(result.get("speech", "Done."), test_mode=test_mode)
        _record(text, result.get("speech", ""), result.get("actions", []))
        return
    # Fall through to existing intent router
    ...
Commit: Add AgentScope-style skills auto-loader with email, calendar, iMessage skills
STEAL 5 — MEMORY COMPRESSION: Replace raw JSONL append with compressed context window.
In memory/store.py add a context compression function:
pythondef get_compressed_context(max_tokens: int = 3000) -> str:
    """Return recent sessions compressed to fit in max_tokens.
    Recent sessions kept verbatim. Older ones summarized by LLM.
    Implements AgentScope memory compression pattern."""
    from brain.ollama_client import _call
    
    sessions = load_recent_sessions(50)
    if not sessions:
        return ""
    
    # Last 5 sessions — keep verbatim
    recent = sessions[-5:]
    older = sessions[:-5]
    
    recent_text = "\n".join(
        f"[{s.get('timestamp','')[:16]}] {s.get('context_preview','')} → {s.get('speech','')}"
        for s in recent
    )
    
    if not older:
        return recent_text
    
    # Older sessions — compress with LLM
    older_text = "\n".join(
        f"{s.get('timestamp','')[:10]}: {s.get('speech','')[:80]}"
        for s in older[-20:]
    )
    
    compressed = _call(
        f"Summarize these past AI assistant sessions into 5 bullet points under 100 words total:\n{older_text}",
        "gemma4:e4b",
        max_tokens=120,
        temperature=0.1,
    )
    
    return f"PAST CONTEXT (compressed):\n{compressed}\n\nRECENT SESSIONS:\n{recent_text}"
In butler.py find where memory context is injected into LLM prompts. Replace load_recent_sessions() call with get_compressed_context(). This keeps the prompt small regardless of how many sessions exist. Commit: Add memory compression — keep context window tight
STEAL 6 — QPM RATE LIMITER: Add concurrency control so Burry never runs out of RAM.
Create mac-butler/brain/rate_limiter.py:
python#!/usr/bin/env python3
"""QPM sliding window rate limiter — stolen from CoPaw/AgentScope pattern.
Prevents OOM crashes when multiple LLM calls stack up.
"""
import asyncio
import threading
import time
from collections import deque

class QPMRateLimiter:
    """Queries-per-minute sliding window with semaphore concurrency control."""
    
    def __init__(self, qpm: int = 10, max_concurrent: int = 2):
        self.qpm = qpm
        self.max_concurrent = max_concurrent
        self._timestamps: deque = deque()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
    
    def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a slot. Blocks if at limit. Returns False if timeout."""
        deadline = time.monotonic() + timeout
        
        while time.monotonic() < deadline:
            with self._lock:
                now = time.monotonic()
                # Remove timestamps older than 60s
                while self._timestamps and self._timestamps[0] < now - 60:
                    self._timestamps.popleft()
                
                if len(self._timestamps) < self.qpm:
                    self._timestamps.append(now)
                    break
            
            # Wait and retry
            time.sleep(0.5)
        else:
            return False
        
        return self._semaphore.acquire(timeout=timeout)
    
    def release(self):
        self._semaphore.release()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, *args):
        self.release()

# Global limiter — max 10 LLM calls per minute, max 2 concurrent
_LLM_LIMITER = QPMRateLimiter(qpm=10, max_concurrent=2)

def get_limiter() -> QPMRateLimiter:
    return _LLM_LIMITER
In brain/ollama_client.py wrap every requests.post() call with the rate limiter:
pythonfrom brain.rate_limiter import get_limiter

def _call(prompt, model, ...):
    limiter = get_limiter()
    with limiter:
        response = requests.post(...)
    return response
Commit: Add QPM rate limiter — prevent RAM crashes on concurrent LLM calls
STEAL 7 — OPENTELEMETRY TRACING: Replace print() with proper distributed tracing.
Create mac-butler/runtime/tracing.py:
python#!/usr/bin/env python3
"""OpenTelemetry tracing — stolen from AgentScope observability pattern.
Every voice command is traced from STT through intent to tool call to TTS.
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

_provider = TracerProvider(resource=Resource.create({"service.name": "burry-os"}))
_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(_provider)

tracer = trace.get_tracer("burry.voice_pipeline")

def trace_command(func):
    """Decorator that wraps a function in an OTel span."""
    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__) as span:
            try:
                result = func(*args, **kwargs)
                span.set_status(trace.StatusCode.OK)
                return result
            except Exception as exc:
                span.set_status(trace.StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise
    return wrapper

def add_event(name: str, attributes: dict = None):
    """Add a named event to the current span."""
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes or {})
In butler.py decorate handle_input() with @trace_command. Add add_event() calls at key points:
pythonfrom runtime.tracing import trace_command, add_event

@trace_command
def handle_input(text: str, ...):
    add_event("stt.complete", {"text": text[:100]})
    # ... intent routing ...
    add_event("intent.resolved", {"intent": intent_name, "confidence": conf})
    # ... tool call ...
    add_event("tool.called", {"tool": tool_name})
    # ... TTS ...
    add_event("tts.start", {"speech": speech[:100]})
Commit: Add OpenTelemetry tracing — full pipeline observability
STEAL 8 — IMESSAGE CHANNEL: Wire CoPaw's iMessage pattern so you can message Burry from iPhone.
Create mac-butler/channels/imessage_channel.py:
python#!/usr/bin/env python3
"""iMessage channel — stolen from CoPaw's channel abstraction.
Polls Messages.app for new messages from approved contacts.
Runs as a background daemon. Sends Burry responses back via iMessage.
"""
import subprocess
import threading
import time
from runtime.telemetry import note_event

APPROVED_CONTACTS = ["your-own-number@icloud.com"]  # Add your iCloud email
POLL_INTERVAL = 5  # seconds

_last_seen_id = None

def _get_latest_message() -> tuple[str, str] | None:
    """Get the most recent iMessage received."""
    script = '''
    tell application "Messages"
        if (count of chats) > 0 then
            set latestChat to item 1 of chats
            if (count of messages of latestChat) > 0 then
                set latestMsg to item -1 of messages of latestChat
                return (id of latestMsg as string) & "|||" & (content of latestMsg) & "|||" & (handle of latestMsg)
            end if
        end if
        return ""
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    raw = result.stdout.strip()
    if not raw or "|||" not in raw:
        return None
    parts = raw.split("|||")
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]  # id, content, sender

def _send_reply(contact: str, message: str):
    script = f'tell application "Messages" to send "{message}" to buddy "{contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)

def _poll_loop():
    global _last_seen_id
    from butler import handle_input
    
    while True:
        try:
            result = _get_latest_message()
            if result:
                msg_id, content, sender = result
                if msg_id != _last_seen_id and sender in APPROVED_CONTACTS:
                    _last_seen_id = msg_id
                    note_event("imessage", f"Received from {sender}: {content[:50]}")
                    # Process through full Burry pipeline
                    response = handle_input(content, test_mode=False, return_speech=True)
                    if response:
                        _send_reply(sender, response)
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)

def start_imessage_channel():
    """Start iMessage polling in background thread."""
    thread = threading.Thread(target=_poll_loop, daemon=True, name="burry-imessage")
    thread.start()
    print("[Channel] iMessage channel started — message Burry from your iPhone")
In butler.py on startup add:
pythonfrom channels.imessage_channel import start_imessage_channel
# Start iMessage channel so you can message Burry from iPhone
try:
    start_imessage_channel()
except Exception:
    pass
Commit: Add iMessage channel — message Burry from iPhone
STEAL 9 — ASYNC HTTP CLIENT: Replace synchronous requests with httpx async.
In brain/ollama_client.py add async variant for non-blocking calls:
pythonimport httpx

async def async_call(prompt: str, model: str, system: str = "", max_tokens: int = 300) -> str:
    """Non-blocking async LLM call via httpx. Never blocks the voice pipeline."""
    payload = {"model": model, "prompt": prompt, "system": system, "stream": False, "options": {"num_predict": max_tokens}}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post("http://localhost:11434/api/generate", json=payload)
            return response.json().get("response", "").strip()
    except httpx.TimeoutException:
        return ""
    except Exception:
        return ""
Wire async_call() in background daemons — heartbeat, ambient, bug_hunter — so they never block the voice pipeline. The voice pipeline keeps using synchronous _call() but background tasks use async_call(). Commit: Add async httpx LLM client for non-blocking background daemons
STEAL 10 — HERMES-STYLE STRUCTURED OUTPUT: Add Pydantic structured output for intent extraction.
Create mac-butler/brain/structured_output.py:
python#!/usr/bin/env python3
"""Hermes-style structured output extraction using Pydantic.
Instead of fragile regex, use LLM to extract structured data from voice commands.
Inspired by NousResearch Hermes tool-calling approach.
"""
import json
import re
from pydantic import BaseModel
from typing import Optional

class EmailIntent(BaseModel):
    recipient: str
    subject: Optional[str] = ""
    body: Optional[str] = ""

class ReminderIntent(BaseModel):
    minutes: int
    message: str

class SearchIntent(BaseModel):
    query: str
    time_sensitive: bool = False

def extract_structured(text: str, schema: type[BaseModel], model: str = "gemma4:e4b") -> BaseModel | None:
    """Use LLM to extract structured data from natural language.
    Falls back to None if extraction fails."""
    from brain.ollama_client import _call
    
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    prompt = f"""Extract information from this text and return ONLY valid JSON matching the schema.
No explanation. No markdown. Just the JSON object.

Schema:
{schema_json}

Text: "{text}"

JSON:"""
    
    raw = _call(prompt, model, max_tokens=150, temperature=0.0)
    
    # Strip markdown if present
    raw = re.sub(r"```json?\s*|\s*```", "", raw).strip()
    
    try:
        data = json.loads(raw)
        return schema(**data)
    except Exception:
        return None
Use this in the email intent handler in intents/router.py as a fallback when regex fails:
pythonfrom brain.structured_output import extract_structured, EmailIntent

# If regex fails to extract subject/body, use LLM extraction
if not subject and not body:
    extracted = extract_structured(text, EmailIntent)
    if extracted:
        recipient = extracted.recipient or recipient
        subject = extracted.subject or subject
        body = extracted.body or body
Commit: Add Hermes-style Pydantic structured output for robust intent extraction
FINAL STEPS — run everything and verify:
bashcd ~/Burry/mac-butler

# 1. Syntax check all new Python files
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
import brain.toolkit
import brain.tools_registry  
import brain.rate_limiter
import brain.structured_output
import agents.runner
import skills
import channels.imessage_channel
import runtime.tracing
print('All imports OK')
"

# 2. Full test suite
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -m unittest discover -s tests 2>&1 | tail -10

# 3. Smoke test toolkit
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
import brain.tools_registry
from brain.toolkit import get_toolkit
tools = get_toolkit().get_tools()
print(f'Toolkit has {len(tools)} tools registered')
for t in tools:
    print(' -', t['function']['name'])
"

# 4. Smoke test skills
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
from skills import load_skills, list_skills, match_skill
load_skills()
print('Registered skills:', list_skills())
skill, entities = match_skill('email vedang@gmail.com with subject test and body hello')
print('Email skill matched:', skill['name'] if skill else 'None')
print('Entities:', entities)
"

# 5. Live butler smoke test
timeout 10 PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python butler.py --command 'what should I work on' 2>&1 | tail -15
Push everything to origin/main. Report final test count, toolkit tool count, skills loaded count, and smoke test results Read the full codebase first. Then implement every item below. This is a multi-day sprint — commit each section separately with full test runs. Do not stop.
INSTALL ALL DEPENDENCIES:
bashcd ~/Burry/mac-butler
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/pip install agentscope agentscope-runtime httpx fastapi uvicorn opentelemetry-sdk opentelemetry-exporter-otlp playwright pydantic crawl4ai
DONE TILL HERE 






NEW TO IMPLEMENT 
PHASE 1 — TOOLKIT + SKILLS (already prompted — verify these are done):
Check if brain/toolkit.py and skills/ directory exist. If not, implement them from the previous prompt. Run smoke test:
bashPYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
from skills import load_skills, match_skill
load_skills()
skill, e = match_skill('email vedang@gmail.com with subject test')
print('Skills working:', bool(skill))
"
PHASE 2 — MCP INTEGRATION: Wire any MCP server as a local callable function.
Create mac-butler/brain/mcp_client.py:
python#!/usr/bin/env python3
"""AgentScope MCP client — wire any MCP server as a local tool.
Burry can now use ANY tool from the 200+ MCP ecosystem.
"""
import asyncio
from typing import Callable

async def get_mcp_tool(server_url: str, tool_name: str, transport: str = "streamable_http") -> Callable:
    """Get any MCP tool as a local Python callable.
    Usage: func = await get_mcp_tool('http://localhost:8000/mcp', 'search')
    """
    from agentscope.mcp import HttpStatelessClient
    client = HttpStatelessClient(
        name=f"mcp_{tool_name}",
        transport=transport,
        url=server_url,
    )
    return await client.get_callable_function(func_name=tool_name)

async def register_mcp_server(server_url: str, toolkit, transport: str = "streamable_http") -> list[str]:
    """Register ALL tools from an MCP server into Burry's toolkit.
    This is the single most powerful line in Burry — 
    one MCP server URL = all its tools instantly available to Burry.
    """
    from agentscope.mcp import HttpStatelessClient
    client = HttpStatelessClient(name="mcp_bulk", transport=transport, url=server_url)
    tools = await client.list_tools()
    registered = []
    for tool in tools:
        func = await client.get_callable_function(func_name=tool.name)
        toolkit.register_tool_function(func)
        registered.append(tool.name)
    return registered

# Pre-configured MCP servers Burry can use
MCP_SERVERS = {
    # Add your own MCP servers here
    # "filesystem": "http://localhost:3001/mcp",
    # "github": "http://localhost:3002/mcp",
    # "slack": "http://localhost:3003/mcp",
}

def load_configured_mcp_servers(toolkit) -> None:
    """Load all configured MCP servers into toolkit at startup."""
    for name, url in MCP_SERVERS.items():
        try:
            loop = asyncio.new_event_loop()
            registered = loop.run_until_complete(register_mcp_server(url, toolkit))
            loop.close()
            print(f"[MCP] Loaded {name}: {len(registered)} tools")
        except Exception as exc:
            print(f"[MCP] Failed to load {name}: {exc}")
In butler.py on startup after load_skills(), add:
pythonfrom brain.mcp_client import load_configured_mcp_servers
from brain.toolkit import get_toolkit
import brain.tools_registry  # noqa
try:
    load_configured_mcp_servers(get_toolkit())
except Exception:
    pass
Commit: Wire AgentScope MCP client — any MCP server becomes a Burry tool
PHASE 3 — BROWSER-USE AGENT: Replace manual Scrapling/Playwright with AgentScope's Browser-use agent.
Create mac-butler/agents/browser_agent.py:
python#!/usr/bin/env python3
"""AgentScope Browser-use agent — autonomous web navigation.
Replaces manual Scrapling/Playwright with an LLM-driven browser agent.
Can: book flights, fill forms, scrape dynamic sites, monitor live data.
"""
import asyncio
from agentscope.agent import ReActAgent
from agentscope.tool import Toolkit
from agentscope.memory import InMemoryMemory

async def browse_and_act(task: str, model_name: str = "gemma4:e4b") -> str:
    """Give Burry a browser task in plain English. It figures out how to do it.
    
    Examples:
    - 'Go to github.com/Aadi262/Burry and tell me the latest commit message'
    - 'Search Hacker News for AI agents and summarize the top 3 posts'
    - 'Open mail.google.com and tell me how many unread emails I have'
    """
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Simple task executor — LLM decides what to do
            from brain.ollama_client import _call
            
            # Get initial page state
            if "http" in task.lower():
                import re
                url_match = re.search(r'https?://\S+', task)
                if url_match:
                    await page.goto(url_match.group(0), wait_until="networkidle", timeout=10000)
            
            # Take screenshot and describe
            screenshot = await page.screenshot(type="png")
            content = await page.content()
            text = await page.evaluate("document.body.innerText")[:3000]
            
            await browser.close()
            
            # LLM synthesizes result
            result = _call(
                f"Task: {task}\n\nPage content:\n{text[:2000]}\n\nAnswer the task concisely:",
                model_name,
                max_tokens=200,
                temperature=0.1,
            )
            return result or text[:500]
    except Exception as exc:
        # Fallback to existing BrowsingAgent
        from browser.agent import BrowsingAgent
        result = BrowsingAgent().search(task, question=task)
        return result.get("result", f"Browser error: {exc}")

def sync_browse(task: str) -> str:
    """Synchronous wrapper for use in tool calls."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(browse_and_act(task))
    finally:
        loop.close()
Register it as a Burry tool in brain/tools_registry.py:
python@tool
def browse_and_act(task: str) -> str:
    """Autonomously browse the web to complete a task. 
    Can navigate, click, fill forms, and extract information from any website."""
    from agents.browser_agent import sync_browse
    return sync_browse(task)
Commit: Add AgentScope-style browser-use agent
PHASE 4 — DEEP RESEARCH AGENT: Multi-step research with memory.
Create mac-butler/agents/research_agent.py:
python#!/usr/bin/env python3
"""Deep Research Agent — inspired by AgentScope's research agent.
Breaks complex questions into subtasks, searches each, synthesizes.
"""
import asyncio
from brain.ollama_client import _call
from browser.agent import BrowsingAgent

def deep_research(question: str, model: str = "gemma4:e4b") -> str:
    """Multi-step research agent.
    1. Decomposes question into 3 search queries
    2. Runs all searches in parallel
    3. Synthesizes into coherent answer
    
    Example: 'What are the latest trends in AI agents and how do they compare?'
    → 3 targeted searches → synthesis → one clear answer
    """
    # Step 1: Decompose into sub-queries
    decompose_prompt = f"""Break this research question into exactly 3 specific web search queries.
Return ONLY the 3 queries, one per line, no numbering or explanation.

Question: {question}

Queries:"""
    
    raw_queries = _call(decompose_prompt, model, max_tokens=100, temperature=0.1)
    queries = [q.strip() for q in raw_queries.strip().split("\n") if q.strip()][:3]
    
    if not queries:
        queries = [question]
    
    # Step 2: Search all queries (parallel via threading)
    import concurrent.futures
    browser = BrowsingAgent()
    
    def search_one(q: str) -> str:
        try:
            result = browser.search(q, question=question)
            return result.get("result", "")
        except Exception:
            return ""
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(search_one, q) for q in queries]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # Step 3: Synthesize
    combined = "\n\n---\n\n".join(r for r in results if r)
    if not combined:
        return "I couldn't find enough information on that topic."
    
    synthesis_prompt = f"""Research question: {question}

Research findings:
{combined[:4000]}

Provide a clear, concise answer in 3-5 sentences covering the key points:"""
    
    answer = _call(synthesis_prompt, model, max_tokens=300, temperature=0.2)
    return answer or combined[:500]
Register as tool:
python@tool
def deep_research(question: str) -> str:
    """Research a complex question by searching multiple sources and synthesizing the answer.
    Best for: 'what are the latest developments in X', 'compare A and B', 'explain the current state of Y'"""
    from agents.research_agent import deep_research as _research
    return _research(question)
Commit: Add deep research agent — multi-step parallel search with synthesis
PHASE 5 — META PLANNER: Decompose complex multi-step tasks.
Create mac-butler/agents/planner_agent.py:
python#!/usr/bin/env python3
"""Meta Planner Agent — inspired by AgentScope's Meta Planner.
Decomposes complex tasks into steps and executes them sequentially.
"""
import json
from brain.ollama_client import _call
from runtime.telemetry import note_event

def plan_and_execute(task: str, ctx: dict, model: str = "gemma4:26b") -> str:
    """Break a complex task into steps and execute them.
    
    Example: 'Set up my morning: open mac-butler in Cursor, 
    play focus music, check VPS status, and remind me of standup in 30 mins'
    → Plan: [open_project, spotify_control, ssh_vps, set_reminder]
    → Execute each step in order
    → Report results
    """
    from brain.toolkit import get_toolkit
    import brain.tools_registry  # noqa
    
    toolkit = get_toolkit()
    available_tools = [t["function"]["name"] for t in toolkit.get_tools()]
    
    # Generate plan
    plan_prompt = f"""You are a task planner. Break this task into 2-5 steps using ONLY these available tools:
{', '.join(available_tools)}

Task: {task}

Return a JSON array of steps. Each step: {{"tool": "tool_name", "args": {{"param": "value"}}, "reason": "why"}}
Return ONLY the JSON array, nothing else:"""
    
    raw_plan = _call(plan_prompt, model, max_tokens=400, temperature=0.1)
    
    try:
        # Clean JSON
        import re
        raw_plan = re.sub(r"```json?\s*|\s*```", "", raw_plan).strip()
        steps = json.loads(raw_plan)
    except Exception:
        return f"I couldn't plan that task. Try breaking it into simpler steps."
    
    # Execute each step
    results = []
    note_event("planner", f"Executing {len(steps)}-step plan for: {task[:50]}")
    
    for i, step in enumerate(steps):
        tool_name = step.get("tool", "")
        args = step.get("args", {})
        
        try:
            result = toolkit.call(tool_name, **args)
            results.append(f"Step {i+1} ({tool_name}): {str(result)[:100]}")
            note_event("planner_step", f"{tool_name}: {str(result)[:50]}")
        except Exception as exc:
            results.append(f"Step {i+1} ({tool_name}): failed — {str(exc)[:50]}")
    
    # Summarize
    summary_prompt = f"""Task completed: {task}
Results: {chr(10).join(results)}

Give a brief 1-2 sentence summary of what was accomplished:"""
    
    summary = _call(summary_prompt, "gemma4:e4b", max_tokens=80, temperature=0.1)
    return summary or f"Completed {len(results)} steps."
Register as tool and add intent pattern:
python@tool
def plan_and_execute(task: str) -> str:
    """Plan and execute a complex multi-step task automatically.
    Use when the request requires multiple actions in sequence."""
    from agents.planner_agent import plan_and_execute as _plan
    from context import build_structured_context
    return _plan(task, {})
In intents/router.py add pattern for complex multi-step commands:
pythonif re.search(r"\b(set up|prepare|do all|everything for|my morning|my routine)\b", lowered):
    return IntentResult("plan_and_execute", {"task": text})
Commit: Add Meta Planner agent — complex tasks broken into steps
PHASE 6 — REME LONG-TERM MEMORY: Proper cross-session memory management.
Create mac-butler/memory/long_term.py:
python#!/usr/bin/env python3
"""ReMe-style long-term memory — inspired by AgentScope's ReMe module.
Manages what Burry remembers across sessions with explicit control.
Three memory tiers:
  - Working: current session (last 6 turns)
  - Recent: last 7 days compressed  
  - Archive: older sessions summarized
"""
import json
import time
from pathlib import Path
from typing import Optional

MEMORY_PATH = Path(__file__).parent / "long_term_memory.json"

def _load() -> dict:
    try:
        return json.loads(MEMORY_PATH.read_text())
    except Exception:
        return {"working": [], "recent": [], "archive": [], "facts": {}, "updated_at": ""}

def _save(data: dict) -> None:
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    MEMORY_PATH.write_text(json.dumps(data, indent=2))

def remember_fact(key: str, value: str) -> None:
    """Store a specific fact Burry should always remember.
    Example: remember_fact('standup_time', '10:30am daily')
    """
    data = _load()
    data["facts"][key] = {"value": value, "stored_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _save(data)

def recall_fact(key: str) -> Optional[str]:
    """Recall a specific stored fact."""
    data = _load()
    fact = data["facts"].get(key)
    return fact["value"] if fact else None

def add_to_working_memory(heard: str, spoken: str) -> None:
    """Add a conversation turn to working memory. Auto-compress when full."""
    data = _load()
    data["working"].append({"heard": heard, "spoken": spoken, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    
    # Keep working memory at 6 turns max
    if len(data["working"]) > 6:
        # Move oldest to recent
        overflow = data["working"][:-6]
        data["recent"].extend(overflow)
        data["working"] = data["working"][-6:]
        
        # Compress recent to archive if too large
        if len(data["recent"]) > 50:
            _compress_recent_to_archive(data)
    
    _save(data)

def _compress_recent_to_archive(data: dict) -> None:
    """Compress recent memory into archive summaries using LLM."""
    from brain.ollama_client import _call
    
    recent_text = "\n".join(
        f"Q: {t['heard']} A: {t['spoken']}"
        for t in data["recent"][-20:]
    )
    
    summary = _call(
        f"Summarize these past conversations into 3 bullet points:\n{recent_text}",
        "gemma4:e4b",
        max_tokens=100,
        temperature=0.1,
    )
    
    if summary:
        data["archive"].append({"summary": summary, "compressed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "turns_count": len(data["recent"])})
        data["recent"] = data["recent"][-10:]  # keep last 10

def get_full_context() -> str:
    """Get complete memory context for LLM injection."""
    data = _load()
    parts = []
    
    if data["facts"]:
        facts_text = "\n".join(f"- {k}: {v['value']}" for k, v in data["facts"].items())
        parts.append(f"REMEMBERED FACTS:\n{facts_text}")
    
    if data["archive"]:
        archive_text = "\n".join(f"- {a['summary']}" for a in data["archive"][-3:])
        parts.append(f"PAST CONTEXT:\n{archive_text}")
    
    if data["recent"]:
        recent_text = "\n".join(f"Q: {t['heard']}\nA: {t['spoken']}" for t in data["recent"][-5:])
        parts.append(f"RECENT SESSIONS:\n{recent_text}")
    
    if data["working"]:
        working_text = "\n".join(f"Q: {t['heard']}\nA: {t['spoken']}" for t in data["working"])
        parts.append(f"CURRENT SESSION:\n{working_text}")
    
    return "\n\n".join(parts)
In butler.py replace the memory context injection with get_full_context(). After every handle_input() response, call add_to_working_memory(heard_text, spoken_text). Commit: Add ReMe-style three-tier long-term memory
PHASE 7 — HUMAN-IN-LOOP STEERING: Let user interrupt Burry mid-task.
In butler.py add interrupt support:
pythonimport asyncio
import threading

_INTERRUPT_EVENT = threading.Event()
_INTERRUPT_MESSAGE = ""

def interrupt_burry(new_command: str) -> None:
    """Interrupt current Burry task with a new command.
    Called from HUD when user types while Burry is executing.
    """
    global _INTERRUPT_MESSAGE
    _INTERRUPT_MESSAGE = new_command
    _INTERRUPT_EVENT.set()
    print(f"[Butler] Interrupted — switching to: {new_command[:50]}")

def check_interrupt() -> Optional[str]:
    """Check if user interrupted. Returns new command if yes, None if no."""
    if _INTERRUPT_EVENT.is_set():
        _INTERRUPT_EVENT.clear()
        msg = _INTERRUPT_MESSAGE
        global _INTERRUPT_MESSAGE
        _INTERRUPT_MESSAGE = ""
        return msg
    return None
In the main LLM call loop in butler.py add interrupt checks between tool calls:
python# After each tool call result, before next tool call:
interrupt = check_interrupt()
if interrupt:
    speak("Switching to your new request.")
    _record(text, "Interrupted by user", [], intent_name="interrupted")
    return handle_input(interrupt, test_mode=test_mode)
In dashboard.py add a POST /api/interrupt endpoint:
pythonelif path == "/api/interrupt" and method == "POST":
    body = json.loads(request.read().decode())
    new_command = body.get("text", "")
    if new_command:
        from butler import interrupt_burry
        interrupt_burry(new_command)
    send_json({"status": "interrupted"})
In commands.js add keyboard shortcut Escape to interrupt:
javascript// When Burry is thinking/executing and user presses Escape:
if (event.key === "Escape" && refs.body.dataset.state !== "idle") {
    const newCmd = refs.commandInput.value.trim();
    if (newCmd) {
        await postCommand({ action: "interrupt", text: newCmd });
        refs.commandInput.value = "";
    }
}
Commit: Add human-in-loop steering — interrupt Burry mid-task
PHASE 8 — A2A PROTOCOL: Make Burry an A2A agent so other agents can call it.
Create mac-butler/channels/a2a_server.py:
python#!/usr/bin/env python3
"""A2A server — makes Burry discoverable by other AI agents.
Any A2A-compatible agent (Google ADK, AgentScope, CrewAI) 
can now call Burry as a specialized Mac operator agent.

Other agents can discover Burry at: http://localhost:3335/agent-card
and call it at: http://localhost:3335/run
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading

AGENT_CARD = {
    "name": "Burry OS",
    "description": "Local AI operator for macOS. Can control apps, run code, manage files, send messages, and interact with the Mac system.",
    "version": "1.0",
    "capabilities": {
        "tools": ["open_project", "focus_app", "run_shell", "send_email", "spotify_control", "git_commit", "browse_web", "deep_research", "plan_and_execute"],
        "voice": True,
        "mac_control": True,
        "local_llm": True,
    },
    "endpoints": {
        "run": "http://localhost:3335/run",
        "agent_card": "http://localhost:3335/agent-card",
    }
}

class A2AHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/agent-card":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(AGENT_CARD).encode())
    
    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode())
            task = body.get("task", "") or body.get("text", "")
            
            if task:
                from butler import handle_input
                handle_input(task, test_mode=False)
                response = {"status": "ok", "agent": "Burry OS", "task": task}
            else:
                response = {"status": "error", "message": "No task provided"}
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, *args):
        pass  # Suppress access logs

def start_a2a_server():
    server = HTTPServer(("localhost", 3335), A2AHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="burry-a2a")
    thread.start()
    print("[A2A] Burry is discoverable at http://localhost:3335/agent-card")
In butler.py on startup add:
pythonfrom channels.a2a_server import start_a2a_server
try:
    start_a2a_server()
except Exception:
    pass
Commit: Add A2A protocol server — Burry becomes discoverable by other AI agents
PHASE 9 — RAG KNOWLEDGE BASE: Give Burry a searchable knowledge base.
Create mac-butler/memory/knowledge_base.py:
python#!/usr/bin/env python3
"""RAG knowledge base — inspired by AgentScope's SimpleKnowledge.
Index local files, docs, and notes. Search them semantically.
Burry can now answer 'what does the IEX ETPS-5326 spec say about X'
by reading your actual documents.
"""
import json
import hashlib
from pathlib import Path
from typing import Optional

KB_PATH = Path(__file__).parent / "knowledge_base"
KB_INDEX = KB_PATH / "index.json"

def _ensure_kb():
    KB_PATH.mkdir(exist_ok=True)
    if not KB_INDEX.exists():
        KB_INDEX.write_text(json.dumps({"documents": [], "chunks": []}))

def index_file(file_path: str, title: str = "") -> int:
    """Add a file to the knowledge base. Returns number of chunks indexed."""
    _ensure_kb()
    path = Path(file_path)
    if not path.exists():
        return 0
    
    text = path.read_text(errors="ignore")
    # Split into chunks of ~500 words
    words = text.split()
    chunks = [" ".join(words[i:i+500]) for i in range(0, len(words), 400)]
    
    data = json.loads(KB_INDEX.read_text())
    
    doc_id = hashlib.md5(file_path.encode()).hexdigest()[:8]
    data["documents"].append({"id": doc_id, "path": file_path, "title": title or path.name, "chunks": len(chunks)})
    
    for i, chunk in enumerate(chunks):
        data["chunks"].append({"doc_id": doc_id, "chunk_id": f"{doc_id}_{i}", "text": chunk, "title": title or path.name})
    
    KB_INDEX.write_text(json.dumps(data, indent=2))
    return len(chunks)

def search_knowledge_base(query: str, top_k: int = 3) -> list[dict]:
    """Search indexed documents. Returns top matching chunks."""
    _ensure_kb()
    data = json.loads(KB_INDEX.read_text())
    chunks = data.get("chunks", [])
    
    if not chunks:
        return []
    
    # Simple keyword scoring (replace with embedding search for production)
    query_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        chunk_words = set(chunk["text"].lower().split())
        score = len(query_words & chunk_words) / max(len(query_words), 1)
        if score > 0:
            scored.append((score, chunk))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]
Register as tool:
python@tool
def search_knowledge_base(query: str) -> str:
    """Search your indexed local documents and notes for relevant information.
    Use for: 'what does the spec say about X', 'find my notes on Y', 'look up Z in my docs'"""
    from memory.knowledge_base import search_knowledge_base as _search
    results = _search(query)
    if not results:
        return "Nothing found in knowledge base. Index files with: index_file('/path/to/file')"
    return "\n\n".join(f"[{r['title']}]: {r['text'][:300]}" for r in results)

@tool
def index_file(file_path: str, title: str = "") -> str:
    """Add a file to Burry's searchable knowledge base."""
    from memory.knowledge_base import index_file as _index
    count = _index(file_path, title)
    return f"Indexed {count} chunks from {file_path}"
Commit: Add RAG knowledge base — Burry can search your local documents
PHASE 10 — PLANNOTEBOOK: Task tracking that persists across sessions.
Create mac-butler/memory/plan_notebook.py:
python#!/usr/bin/env python3
"""PlanNotebook — inspired by AgentScope's PlanNotebook.
Tracks multi-step plans across sessions. Burry remembers 
what it was doing and picks up where it left off.
"""
import json
import time
from pathlib import Path
from typing import Optional

NOTEBOOK_PATH = Path(__file__).parent / "plan_notebook.json"

def _load() -> dict:
    try:
        return json.loads(NOTEBOOK_PATH.read_text())
    except Exception:
        return {"active_plans": [], "completed_plans": []}

def _save(data: dict) -> None:
    NOTEBOOK_PATH.write_text(json.dumps(data, indent=2))

def create_plan(title: str, steps: list[str]) -> str:
    """Create a new multi-step plan."""
    data = _load()
    plan = {
        "id": f"plan_{int(time.time())}",
        "title": title,
        "steps": [{"text": s, "done": False, "started_at": None, "completed_at": None} for s in steps],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "active",
    }
    data["active_plans"].append(plan)
    _save(data)
    return plan["id"]

def get_current_plan() -> Optional[dict]:
    """Get the most recent active plan."""
    data = _load()
    active = [p for p in data["active_plans"] if p["status"] == "active"]
    return active[-1] if active else None

def advance_plan(plan_id: str) -> Optional[str]:
    """Mark current step done, return next step text."""
    data = _load()
    for plan in data["active_plans"]:
        if plan["id"] == plan_id:
            for step in plan["steps"]:
                if not step["done"]:
                    step["done"] = True
                    step["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    break
            # Find next undone step
            next_steps = [s for s in plan["steps"] if not s["done"]]
            if not next_steps:
                plan["status"] = "completed"
                data["completed_plans"].append(plan)
                data["active_plans"].remove(plan)
                _save(data)
                return None
            _save(data)
            return next_steps[0]["text"]
    return None

def get_plan_status() -> str:
    """Get readable status of current plan for HUD display."""
    plan = get_current_plan()
    if not plan:
        return "No active plan"
    done = sum(1 for s in plan["steps"] if s["done"])
    total = len(plan["steps"])
    next_step = next((s["text"] for s in plan["steps"] if not s["done"]), "All done")
    return f"{plan['title']}: {done}/{total} steps. Next: {next_step}"
Wire get_plan_status() into the HUD ambient panel — show current plan progress alongside ambient bullets. Commit: Add PlanNotebook — multi-step plans that persist across sessions
PHASE 11 — AGENTIC RL FOUNDATION: Self-improvement loop.
Create mac-butler/memory/rl_loop.py:
python#!/usr/bin/env python3
"""Agentic RL foundation — inspired by AgentScope's Trinity-RFT integration.
Burry tracks what works and what doesn't, and improves over time.
Not full RL training — but a feedback loop that makes Burry smarter.

Pattern: outcome → score → adjust → improve
"""
import json
import time
from pathlib import Path

RL_PATH = Path(__file__).parent / "rl_experience.json"

def _load() -> dict:
    try:
        return json.loads(RL_PATH.read_text())
    except Exception:
        return {"episodes": [], "intent_scores": {}, "model_scores": {}}

def _save(data: dict) -> None:
    RL_PATH.write_text(json.dumps(data, indent=2))

def record_episode(text: str, intent: str, model: str, response: str, outcome: str = "unknown") -> None:
    """Record a completed command episode.
    outcome: 'success', 'failure', 'partial', 'unknown'
    """
    data = _load()
    
    episode = {
        "text": text[:100],
        "intent": intent,
        "model": model,
        "response": response[:100],
        "outcome": outcome,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    
    data["episodes"].append(episode)
    data["episodes"] = data["episodes"][-500:]  # keep last 500
    
    # Update intent scores
    if intent not in data["intent_scores"]:
        data["intent_scores"][intent] = {"success": 0, "failure": 0, "total": 0}
    data["intent_scores"][intent]["total"] += 1
    if outcome == "success":
        data["intent_scores"][intent]["success"] += 1
    elif outcome == "failure":
        data["intent_scores"][intent]["failure"] += 1
    
    # Update model scores
    if model not in data["model_scores"]:
        data["model_scores"][model] = {"success": 0, "failure": 0, "latency_sum": 0, "total": 0}
    data["model_scores"][model]["total"] += 1
    if outcome == "success":
        data["model_scores"][model]["success"] += 1
    
    _save(data)

def get_best_model_for_intent(intent: str, candidates: list[str]) -> str:
    """Return the model with best success rate for this intent type."""
    data = _load()
    model_scores = data.get("model_scores", {})
    
    best = candidates[0]
    best_rate = 0.0
    
    for model in candidates:
        scores = model_scores.get(model, {})
        total = scores.get("total", 0)
        if total >= 5:  # Need at least 5 episodes to trust
            rate = scores.get("success", 0) / total
            if rate > best_rate:
                best_rate = rate
                best = model
    
    return best

def get_improvement_hints() -> str:
    """Generate improvement hints from episode history."""
    data = _load()
    intent_scores = data.get("intent_scores", {})
    
    hints = []
    for intent, scores in intent_scores.items():
        total = scores.get("total", 0)
        failures = scores.get("failure", 0)
        if total >= 3 and failures / total > 0.5:
            hints.append(f"- {intent} intent fails {int(failures/total*100)}% of the time — needs improvement")
    
    return "\n".join(hints) if hints else "All intents performing well"
Wire record_episode() into butler.py after every handle_input() completes. Use get_best_model_for_intent() in ollama_client.py to select models dynamically. Commit: Add agentic RL experience loop — Burry tracks what works and improves
FINAL VERIFICATION — run everything:
bashcd ~/Burry/mac-butler

# 1. All imports work
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
import brain.mcp_client
import agents.browser_agent
import agents.research_agent
import agents.planner_agent
import memory.long_term
import memory.knowledge_base
import memory.plan_notebook
import memory.rl_loop
import channels.a2a_server
print('All 9 new modules import OK')
"

# 2. Full test suite
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -m unittest discover -s tests 2>&1 | tail -5

# 3. Toolkit has all tools
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
import brain.tools_registry
from brain.toolkit import get_toolkit
tools = get_toolkit().get_tools()
print(f'Toolkit: {len(tools)} tools registered')
names = [t[\"function\"][\"name\"] for t in tools]
print('Tools:', ', '.join(names))
"

# 4. Skills auto-load
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
from skills import load_skills, list_skills
load_skills()
skills = list_skills()
print(f'Skills: {len(skills)} loaded')
for s in skills:
    print(' -', s)
"

# 5. Deep research works
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
from agents.research_agent import deep_research
result = deep_research('What is AgentScope')
print('Research result:', result[:200])
"

# 6. Butler starts without crash
timeout 10 PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python butler.py --command 'what should I work on' 2>&1 | tail -10

# 7. A2A server starts
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
from channels.a2a_server import start_a2a_server
start_a2a_server()
import time; time.sleep(1)
import urllib.request
resp = urllib.request.urlopen('http://localhost:3335/agent-card')
print('A2A agent card:', resp.read().decode()[:200])
"
Push all commits to origin/main. Report:
- Final test count
- Number of tools in toolkit
- Number of skills loaded
- A2A agent card response
- Butler smoke test output







Skip to content
agentscope-ai
agentscope
Repository navigation
Code
Issues
128
 (128)
Pull requests
45
 (45)
Discussions
Actions
Projects
Security and quality
Insights
Important update
On April 24 we'll start using GitHub Copilot interaction data for AI model training unless you opt out. Review this update and manage your preferences in your GitHub account settings.
Owner avatar
agentscope
Public
agentscope-ai/agentscope
Go to file
t
Name		
alex-xinlu
alex-xinlu
fix(example): correct field name in ReflectFailure decomposition outp…
035de11
 · 
4 days ago
.gemini
ci(gemini): add code review guide for the gemini code assist (#1135)
3 months ago
.github
feat(formatter): support local multimedia paths starting with "file:/…
last week
assets/images
docs(readme): update the README.md and README_zh.md with copaw (#1353)
2 weeks ago
docs
feat(memory): add tablestore memory support (#1308)
5 days ago
examples
fix(example): correct field name in ReflectFailure decomposition outp…
4 days ago
src/agentscope
feat(memory): add tablestore memory support (#1308)
5 days ago
tests
feat(memory): add tablestore memory support (#1308)
5 days ago
.gitignore
feat(a2ui): add a2ui example in agentscope (#1101)
3 months ago
.pre-commit-config.yaml
Add uv package manager support in AgentScope (#847)
6 months ago
CONTRIBUTING.md
feat(memory): add tablestore memory support (#1308)
5 days ago
CONTRIBUTING_zh.md
feat(memory): add tablestore memory support (#1308)
5 days ago
LICENSE
[HOTFIX] Fix the bug in pre-commit workflow; Resolve ``execute_shell_…
8 months ago
README.md
docs(copaw): add news about copaw (#1379)
last week
README_zh.md
docs(copaw): add news about copaw (#1379)
last week
pyproject.toml
feat(memory): add tablestore memory support (#1308)
5 days ago
Repository files navigation
README
Contributing
Apache-2.0 license
AgentScope Logo

中文主页 | Tutorial | Roadmap (Jan 2026 -) | FAQ

arxiv pypi pypi discord docs license

agentscope-ai%2Fagentscope | Trendshift

What is AgentScope?
AgentScope is a production-ready, easy-to-use agent framework with essential abstractions that work with rising model capability and built-in support for finetuning.

We design for increasingly agentic LLMs. Our approach leverages the models' reasoning and tool use abilities rather than constraining them with strict prompts and opinionated orchestrations.

Why use AgentScope?
Simple: start building your agents in 5 minutes with built-in ReAct agent, tools, skills, human-in-the-loop steering, memory, planning, realtime voice, evaluation and model finetuning
Extensible: large number of ecosystem integrations for tools, memory and observability; built-in support for MCP and A2A; message hub for flexible multi-agent orchestration and workflows
Production-ready: deploy and serve your agents locally, as serverless in the cloud, or on your K8s cluster with built-in OTel support

The AgentScope Ecosystem

News
[2026-03] RELS: We recently developed and open sourced an AI assistant named CoPaw (Co Personal Agent Workstation), built upon AgentScope, AgentScope-Runtime, and Reme.
[2026-02] FEAT: Realtime Voice Agent support. Example | Multi-Agent Realtime Example | Tutorial
[2026-01] COMM: Biweekly Meetings launched to share ecosystem updates and development plans - join us! Details & Schedule
[2026-01] FEAT: Database support & memory compression in memory module. Example | Tutorial
[2025-12] INTG: A2A (Agent-to-Agent) protocol support. Example | Tutorial
[2025-12] FEAT: TTS (Text-to-Speech) support. Example | Tutorial
[2025-11] INTG: Anthropic Agent Skill support. Example | Tutorial
[2025-11] RELS: Alias-Agent for diverse real-world tasks and Data-Juicer Agent for data processing open-sourced. Alias-Agent | Data-Juicer Agent
[2025-11] INTG: Agentic RL via Trinity-RFT library. Example | Trinity-RFT
[2025-11] INTG: ReMe for enhanced long-term memory. Example
[2025-11] RELS: agentscope-samples repository launched and agentscope-runtime upgraded with Docker/K8s deployment and VNC-powered GUI sandboxes. Samples | Runtime
More news →

Community
Welcome to join our community on

Discord	DingTalk
	
📑 Table of Contents
Quickstart
Installation
From PyPI
From source
Example
Hello AgentScope!
Voice Agent
Realtime Voice Agent
Human-in-the-loop
Flexible MCP Usage
Agentic RL
Multi-Agent Workflows
Documentation
More Examples & Samples
Functionality
Agent
Game
Workflow
Evaluation
Tuner
Contributing
License
Publications
Contributors
Quickstart
Installation
AgentScope requires Python 3.10 or higher.

From PyPI
pip install agentscope
Or with uv:

uv pip install agentscope
From source
# Pull the source code from GitHub
git clone -b main https://github.com/agentscope-ai/agentscope.git

# Install the package in editable mode
cd agentscope

pip install -e .
# or with uv:
# uv pip install -e .
Example
Hello AgentScope!
Start with a conversation between user and a ReAct agent 🤖 named "Friday"!

from agentscope.agent import ReActAgent, UserAgent
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.tool import Toolkit, execute_python_code, execute_shell_command
import os, asyncio


async def main():
    toolkit = Toolkit()
    toolkit.register_tool_function(execute_python_code)
    toolkit.register_tool_function(execute_shell_command)

    agent = ReActAgent(
        name="Friday",
        sys_prompt="You're a helpful assistant named Friday.",
        model=DashScopeChatModel(
            model_name="qwen-max",
            api_key=os.environ["DASHSCOPE_API_KEY"],
            stream=True,
        ),
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=toolkit,
    )

    user = UserAgent(name="user")

    msg = None
    while True:
        msg = await agent(msg)
        msg = await user(msg)
        if msg.get_text_content() == "exit":
            break

asyncio.run(main())
Voice Agent
Create a voice-enabled ReAct agent that can understand and respond with speech, even playing a multi-agent werewolf game with voice interactions.

 werewolf_voice_agent.mp4 
Realtime Voice Agent
Build a realtime voice agent with web interface that can interact with users via voice input and output.

Realtime chatbot | Realtime Multi-Agent Example

 multi_agent_realtime_voice.mp4 
Human-in-the-loop
Support realtime interruption in ReActAgent: conversation can be interrupted via cancellation in realtime and resumed seamlessly via robust memory preservation.

Realtime Steering

Flexible MCP Usage
Use individual MCP tools as local callable functions to compose toolkits or wrap into a more complex tool.

from agentscope.mcp import HttpStatelessClient
from agentscope.tool import Toolkit
import os

async def fine_grained_mcp_control():
    # Initialize the MCP client
    client = HttpStatelessClient(
        name="gaode_mcp",
        transport="streamable_http",
        url=f"https://mcp.amap.com/mcp?key={os.environ['GAODE_API_KEY']}",
    )

    # Obtain the MCP tool as a **local callable function**, and use it anywhere
    func = await client.get_callable_function(func_name="maps_geo")

    # Option 1: Call directly
    await func(address="Tiananmen Square", city="Beijing")

    # Option 2: Pass to agent as a tool
    toolkit = Toolkit()
    toolkit.register_tool_function(func)
    # ...

    # Option 3: Wrap into a more complex tool
    # ...
Agentic RL
Train your agentic application seamlessly with Reinforcement Learning integration. We also prepare multiple sample projects covering various scenarios:

Example	Description	Model	Training Result
Math Agent	Tune a math-solving agent with multi-step reasoning.	Qwen3-0.6B	Accuracy: 75% → 85%
Frozen Lake	Train an agent to navigate the Frozen Lake environment.	Qwen2.5-3B-Instruct	Success rate: 15% → 86%
Learn to Ask	Tune agents using LLM-as-a-judge for automated feedback.	Qwen2.5-7B-Instruct	Accuracy: 47% → 92%
Email Search	Improve tool-use capabilities without labeled ground truth.	Qwen3-4B-Instruct-2507	Accuracy: 60%
Werewolf Game	Train agents for strategic multi-agent game interactions.	Qwen2.5-7B-Instruct	Werewolf win rate: 50% → 80%
Data Augment	Generate synthetic training data to enhance tuning results.	Qwen3-0.6B	AIME-24 accuracy: 20% → 60%
Multi-Agent Workflows
AgentScope provides MsgHub and pipelines to streamline multi-agent conversations, offering efficient message routing and seamless information sharing

from agentscope.pipeline import MsgHub, sequential_pipeline
from agentscope.message import Msg
import asyncio

async def multi_agent_conversation():
    # Create agents
    agent1 = ...
    agent2 = ...
    agent3 = ...
    agent4 = ...

    # Create a message hub to manage multi-agent conversation
    async with MsgHub(
        participants=[agent1, agent2, agent3],
        announcement=Msg("Host", "Introduce yourselves.", "assistant")
    ) as hub:
        # Speak in a sequential manner
        await sequential_pipeline([agent1, agent2, agent3])
        # Dynamic manage the participants
        hub.add(agent4)
        hub.delete(agent3)
        await hub.broadcast(Msg("Host", "Goodbye!", "assistant"))

asyncio.run(multi_agent_conversation())
Documentation
Tutorial
FAQ
API Docs
More Examples & Samples
Functionality
MCP
Anthropic Agent Skill
Plan
Structured Output
RAG
Long-Term Memory
Session with SQLite
Stream Printing Messages
TTS
Code-first Deployment
Memory Compression
Agent
ReAct Agent
Voice Agent
Deep Research Agent
Browser-use Agent
Meta Planner Agent
A2A Agent
Realtime Voice Agent
Game
Nine-player Werewolves
Workflow
Multi-agent Debate
Multi-agent Conversation
Multi-agent Concurrent
Multi-agent Realtime Conversation
Evaluation
ACEBench
Tuner
Tune ReAct Agent
Contributing
We welcome contributions from the community! Please refer to our CONTRIBUTING.md for guidelines on how to contribute.

License
AgentScope is released under Apache License 2.0.

Publications
If you find our work helpful for your research or application, please cite our papers.

AgentScope 1.0: A Developer-Centric Framework for Building Agentic Applications

AgentScope: A Flexible yet Robust Multi-Agent Platform

@article{agentscope_v1,
    author  = {Dawei Gao, Zitao Li, Yuexiang Xie, Weirui Kuang, Liuyi Yao, Bingchen Qian, Zhijian Ma, Yue Cui, Haohao Luo, Shen Li, Lu Yi, Yi Yu, Shiqi He, Zhiling Luo, Wenmeng Zhou, Zhicheng Zhang, Xuguang He, Ziqian Chen, Weikai Liao, Farruh Isakulovich Kushnazarov, Yaliang Li, Bolin Ding, Jingren Zhou}
    title   = {AgentScope 1.0: A Developer-Centric Framework for Building Agentic Applications},
    journal = {CoRR},
    volume  = {abs/2508.16279},
    year    = {2025},
}

@article{agentscope,
    author  = {Dawei Gao, Zitao Li, Xuchen Pan, Weirui Kuang, Zhijian Ma, Bingchen Qian, Fei Wei, Wenhao Zhang, Yuexiang Xie, Daoyuan Chen, Liuyi Yao, Hongyi Peng, Zeyu Zhang, Lin Zhu, Chen Cheng, Hongzhu Shi, Yaliang Li, Bolin Ding, Jingren Zhou}
    title   = {AgentScope: A Flexible yet Robust Multi-Agent Platform},
    journal = {CoRR},
    volume  = {abs/2402.14034},
    year    = {2024},
}
Contributors
All thanks to our contributors:


About
Build and run agents you can see, understand and trust.

doc.agentscope.io/
Topics
agent mcp chatbot multi-agent multi-modal large-language-models llm llm-agent react-agent
Resources
 Readme
License
 Apache-2.0 license
Contributing
 Contributing
 Activity
 Custom properties
Stars
 23k stars
Watchers
 145 watching
Forks
 2.4k forks
Report repository
Releases 33
v1.0.18
Latest
2 weeks ago
+ 32 releases
Deployments
500+
 github-pages 4 days ago
+ more deployments
Contributors
61
@DavdGao
@qbc2016
@Osier-Yi
@pan-x-c
@zhijianma
@YingchaoX
@gemini-code-assist[bot]
@Luohh5
@ZiTao-Li
@jinliyl
@cuiyuebing
@garyzhang99
@idontwanttosayaword
@denverdino
+ 47 contributors
Languages
Python
100.0%
Footer
© 2026 GitHub, Inc.
Footer navigation
Terms
Privacy
Security
Status
Community
Docs
Contact
Manage cookies
Do not share my personal information
