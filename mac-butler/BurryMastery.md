# Burry OS — Master Architecture Document
## Vision + Codebase Reality Combined

---

## What Burry Is Today vs What It Becomes

Today: voice loop → regex intent → blocking LLM call → TTS → HUD polls stale JSON
Tomorrow: always-on operator that acts, remembers, browses, sees, and reports back

The gap is 10 specific fixes. Each one is independent. Stack them in order.

---

## FIX 1 — Multi-turn voice context (biggest UX impact, one function)

**What's broken:**
`ConversationContext.turns` exists in `butler.py` but turns are never fed into
the planner or speech prompts. Every clap trigger is stateless from the LLM's
perspective. Say "open mac-butler" then "now run the tests" — second turn has
zero context.

**The fix:**
```python
# In butler.py — build_plan_prompt(), inject before the task line:
RECENT_TURNS = "\n".join([
    f"{t['role'].upper()}: {t['text']}"
    for t in context.turns[-5:]  # last 5 turns
])

plan_prompt = f"""
RECENT CONVERSATION:
{RECENT_TURNS}

CURRENT REQUEST: {heard_text}
FOCUS PROJECT: {focus_project}
...rest of prompt
"""
```

Do this first. Nothing else in the system changes. Multi-turn conversation works.

---

## FIX 2 — Semantic memory search (zero new dependencies)

**What's broken:**
`nomic-embed-text` is configured in `butler_config` but never called anywhere.
`search_sessions()` is keyword grep across 7 JSONL files. "Show me recent wins"
finds nothing because no session has the exact word "wins".

**The fix:**
```python
# memory/store.py — add embed-on-write

import ollama

def embed(text: str) -> list[float]:
    resp = ollama.embeddings(model='nomic-embed-text', prompt=text)
    return resp['embedding']

def cosine(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = sum(x**2 for x in a)**0.5
    nb = sum(x**2 for x in b)**0.5
    return dot/(na*nb) if na*nb else 0

# On every memory write — store embedding alongside entry
def store_command(text, result, project):
    entry = {
        "text": text,
        "result": result,
        "project": project,
        "ts": time.time(),
        "embedding": embed(f"{text} {result}")  # add this line
    }
    # ...existing write logic

# Replace search_sessions() with:
def semantic_search(query: str, n: int = 5) -> list:
    q_embed = embed(query)
    scored = []
    for entry in load_all_sessions():
        if "embedding" in entry:
            score = cosine(q_embed, entry["embedding"])
            scored.append((score, entry))
    scored.sort(reverse=True)
    return [e for _, e in scored[:n]]
```

Now "what did we decide about auth" finds the right session entry.

---

## FIX 3 — Gemma 4 model swap + MLX direct path

**What's broken:**
phi4-mini is slower and dumber than gemma4:4b at the same size.
Ollama HTTP round-trip adds 200-400ms to the most latency-sensitive step.

**Model routing table — rewrite `brain/__init__.py`:**
```python
MODELS = {
    "voice":     "gemma4:4b",      # was phi4-mini — faster, better instruction following
    "planning":  "gemma4:12b",     # was qwen2.5:14b — better JSON, faster on M-series
    "reasoning": "deepseek-r1:14b",# keep — deep code review and architecture only
    "agents":    "gemma4:4b",      # HN, Reddit, memory consolidation agents
    "heartbeat": "gemma4:4b",      # re-enable heartbeat.py with this
    "bugfinder": "gemma4:4b",      # re-enable bug_hunter.py with this
}
```

**MLX direct path for voice (kills HTTP overhead):**
```python
# ollama_client.py — add MLX backend

try:
    from mlx_lm import load, generate
    _mlx_model, _mlx_tokenizer = load("mlx-community/gemma-4-4b-it-4bit")
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

def call_voice(prompt: str) -> str:
    if MLX_AVAILABLE:
        return generate(_mlx_model, _mlx_tokenizer, prompt=prompt, max_tokens=80)
    return call_ollama("gemma4:4b", prompt)  # fallback
```

Voice response latency drops from ~2s to ~400ms on M-series Mac.

**Re-enable heartbeat and bug hunter:**
Both are disabled because they used qwen2.5:14b — too heavy for background.
With gemma4:4b they run in ~400ms. In both files:
```python
HEARTBEAT_ENABLED = True
HEARTBEAT_MODEL = "gemma4:4b"
```

---

## FIX 4 — Bridge mac_activity → runtime_state (HUD shows real data)

**What's broken:**
`mac_activity.py` reads frontmost app, workspace, focus project via AppleScript
into its own internal state. Never writes to `runtime_state.json`.
HUD workspace panel shows "Unknown" for everything.

**The fix — one function in `context/watcher.py`:**
```python
def tick(self):
    state = mac_activity.get_state_for_context()
    # existing internal update...

    # ADD THIS:
    rt = load_runtime_state()
    rt["workspace"] = {
        "focus_project": state.get("focus_project", "unknown"),
        "frontmost_app": state.get("frontmost_app", "unknown"),
        "workspace":     state.get("workspace", "unknown"),
    }
    save_runtime_state(rt)
```

HUD workspace panel goes from "Unknown" to live data. One bridge call.

---

## FIX 5 — WebSocket push (HUD feels live, not 2s stale)

**What's broken:**
Dashboard polls `/api/operator` every 2s. Butler writes `runtime_state.json`
on every state change. There's a structural 2s lag on everything.

**The fix — add WS to dashboard server:**
```python
# projects/dashboard.py — add WebSocket broadcast

import threading
import json
from http.server import BaseHTTPRequestHandler
# add: pip install simple-websocket-server
from SimpleWebSocketServer import SimpleWebSocketServer, WebSocket

WS_CLIENTS = set()

class BurryWS(WebSocket):
    def handleConnected(self):
        WS_CLIENTS.add(self)
    def handleClose(self):
        WS_CLIENTS.discard(self)

def broadcast(event: dict):
    dead = set()
    for client in WS_CLIENTS:
        try:
            client.sendMessage(json.dumps(event))
        except:
            dead.add(client)
    WS_CLIENTS -= dead

# In butler.py — after every state change:
# broadcast({"type": "state", "state": current_state, "text": spoken_text})
# broadcast({"type": "transcript", "role": "burry", "text": response})

# In app.js — replace polling with:
const ws = new WebSocket('ws://127.0.0.1:3334/ws');
ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === 'state') setButlerState(event.state);
    if (event.type === 'transcript') appendTranscript(event);
};
```

HUD updates in <50ms instead of up to 2s.

---

## FIX 6 — Async agent fan-out (kills 8-15s silence)

**What's broken:**
When Burry runs a news agent or VPS check, it blocks the entire voice pipeline.
User hears silence for 8-15 seconds. Feels broken.

**The fix:**
```python
# agents/runner.py — wrap agent calls in async

import asyncio
import threading

def run_agent_async(agent_name: str, callback=None):
    def _run():
        result = run_agent(agent_name)  # existing sync call
        # post result to runtime_state
        rt = load_runtime_state()
        rt["last_agent_result"] = {"agent": agent_name, "result": result, "ts": time.time()}
        save_runtime_state(rt)
        if callback:
            callback(result)
        # WS broadcast when done
        broadcast({"type": "agent_result", "agent": agent_name, "result": result})

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

# In butler.py intent handler — instead of blocking:
# BEFORE: result = run_agent("news")
# AFTER:
speak("I'm pulling AI news in the background — check the HUD in a moment")
run_agent_async("news")
# returns immediately, result appears in HUD when ready
```

---

## FIX 7 — Model pre-warming on clap (free latency reduction)

**What's broken:**
Clap detected → STT runs (1-2s) → Ollama model is cold → planning call waits
for model to load. Net: 1-3s of extra perceived latency before any response.

**The fix — fire keep-alive on clap signal:**
```python
# In voice/listener.py — on clap detection:
def on_clap_detected():
    # Immediately fire keep-alive to warm the planning model
    threading.Thread(
        target=lambda: ollama.generate(model='gemma4:12b', prompt=' ', keep_alive='10m'),
        daemon=True
    ).start()
    # Then run STT as normal
    run_stt()
```

By the time STT finishes transcribing (~1-2s), the model is warm.
Saves 0.5-1.5s off every single interaction. Zero downside.

---

## FIX 8 — Native tool calling (replace fragile regex router)

**What's broken:**
`intents/` is pure regex pattern matching. "Check if my VPS is up" → maps to
nothing, falls through to LLM planner cold. Edge cases break constantly.

**The fix — Ollama native tool schema:**
```python
# brain/tools.py — new file

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_project",
            "description": "Open a project in the editor by name",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a safe shell command in a project directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "project": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": "Search the web or fetch and summarize a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "url":   {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search past sessions and memory for relevant context",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":   {"type": "string"},
                    "project": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot_and_describe",
            "description": "Take a screenshot of the current screen and describe it",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

# In butler.py — replace two-stage planner with:
def process_command(heard_text: str, context: ConversationContext):
    messages = build_messages(context, heard_text)  # includes last 5 turns

    response = ollama.chat(
        model='gemma4:12b',
        messages=messages,
        tools=TOOLS
    )

    if response.message.tool_calls:
        for tool_call in response.message.tool_calls:
            result = execute_tool(tool_call.function.name, tool_call.function.arguments)
            messages.append({"role": "tool", "content": str(result)})
        # Get final spoken response after tool execution
        final = ollama.chat(model='gemma4:4b', messages=messages)
        speak(final.message.content)
    else:
        speak(response.message.content)

    # Always store to memory
    memory.store_command(heard_text, response.message.content, context.focus_project)
```

Intent router goes from 40+ regex patterns to 5 clean tool definitions.
Handles any phrasing. Never falls through to garbage.

---

## FIX 9 — Real browsing via tiered scraper stack

**What's broken:**
HN/Reddit/GitHub trending are custom scrapers that break constantly when sites
update their HTML. No ability to fetch arbitrary URLs. Raw Playwright dumps messy
HTML into the LLM wasting tokens and getting bad answers.

**Install — one time:**
```bash
pip install "scrapling[fetchers]" crawl4ai
scrapling install   # installs camoufox stealth browser
crawl4ai-setup      # installs playwright + chromium
```

**The fix:**
```python
# browser/agent.py — new file
import asyncio
import requests
from scrapling.fetchers import Fetcher, StealthyFetcher
from crawl4ai import AsyncWebCrawler
from crawl4ai.content_filter_strategy import BM25ContentFilter

# Tier 1 — Scrapling fast HTTP (no browser, instant)
# Use for: HN, Reddit, GitHub, any static site
# Adaptive selectors — never breaks when site updates HTML
def _fetch_static(url: str) -> str:
    try:
        page = Fetcher.get(url, stealthy_headers=True, follow_redirects=True)
        return page.get_all_text(separator="\n")[:10000]
    except Exception:
        return ""

# Tier 2 — Scrapling stealth browser (Cloudflare bypass)
# Use for: sites that block plain HTTP, paywalled pages, Twitter
# Uses camoufox with fingerprint spoofing — no external CAPTCHA service needed
def _fetch_stealth(url: str) -> str:
    try:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
        return page.get_all_text(separator="\n")[:10000]
    except Exception:
        return ""

# Tier 3 — Crawl4AI LLM-ready markdown (best quality for LLM input)
# BM25 filter keeps only sections relevant to the query — fewer tokens, better answers
# Use this as the final pass before feeding text to gemma4
async def _fetch_llm_ready(url: str, query: str) -> str:
    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(
                url=url,
                word_count_threshold=10,
                content_filter=BM25ContentFilter(
                    user_query=query,
                    bm25_threshold=1.2
                ),
                bypass_cache=True,
            )
        return result.markdown[:8000] if result.success else ""
    except Exception:
        return ""

def fetch_url(url: str, query: str = "") -> str:
    # Try fast first, escalate to stealth, always clean with crawl4ai
    text = _fetch_static(url)
    if not text or len(text) < 200:
        text = _fetch_stealth(url)
    if query:
        # Run crawl4ai over the same URL for LLM-ready filtered markdown
        clean = asyncio.run(_fetch_llm_ready(url, query))
        if clean:
            return clean
    return text

class BrowsingAgent:
    def search(self, query: str) -> str:
        urls = self._searxng(query)
        summaries = []
        for url in urls[:3]:
            text = fetch_url(url, query=query)
            if not text:
                continue
            summary = ollama_call('gemma4:e4b',
                f"Answer '{query}' using only this content:\n\n{text}")
            summaries.append(summary)
        return "\n\n".join(summaries) if summaries else "No results found."

    def fetch(self, url: str, question: str) -> str:
        text = fetch_url(url, query=question)
        return ollama_call('gemma4:e4b',
            f"From this page, answer: '{question}'\n\n{text}")

    def _searxng(self, query: str) -> list[str]:
        try:
            resp = requests.get('http://localhost:8080/search',
                params={'q': query, 'format': 'json'}, timeout=5)
            return [r['url'] for r in resp.json().get('results', [])[:5]]
        except Exception:
            return []

# Wire to browse_web tool in brain/tools.py
# fetch_url() is also used to replace all existing HN/Reddit/GitHub scrapers —
# delete agents/hacker_news.py, agents/reddit.py, agents/github_trending.py
# and replace each with BrowsingAgent().search("topic") calls

# Fetcher priority summary:
# Scrapling Fetcher     → static sites, fastest, adaptive HTML parsing, never breaks on DOM changes
# Scrapling Stealth     → Cloudflare sites, fingerprint spoofing, no external service needed
# Crawl4AI BM25        → final LLM-ready pass, filters irrelevant content, smallest token count
# SearXNG              → search engine, already running locally, zero cost
```

---

## FIX 10 — Screenshot vision (Burry sees your screen)

**What's broken:**
Burry reads AppleScript to know frontmost app name but can't see the screen.
"What am I looking at" → reads process name only.

**The fix:**
```python
# agents/vision.py — new file
import subprocess
import base64
import ollama

def describe_screen(question: str = "What is on the screen right now?") -> str:
    # Take screenshot silently
    subprocess.run(['screencapture', '-x', '-t', 'png', '/tmp/burry_screen.png'],
                   capture_output=True)

    with open('/tmp/burry_screen.png', 'rb') as f:
        image_b64 = base64.b64encode(f.read()).decode()

    response = ollama.chat(
        model='gemma4:12b',  # multimodal variant
        messages=[{
            'role': 'user',
            'content': question,
            'images': [image_b64]
        }]
    )
    return response.message.content

# Wire to take_screenshot_and_describe tool
# Voice trigger: "what am I looking at" / "what's on my screen" / "describe this"
```

---

## NEW FRONTEND PANELS (wire to new capabilities)

### Live Tool Stream panel (center, below transcript)
Shows Burry's tool calls in real time via WebSocket:
```
▶ recall_memory("auth flow decision") ...     [animated spinner]
✓ Found 3 relevant sessions                   [green check, 0.8s]
▶ browse_web("JWT vs sessions tradeoffs") ... [animated spinner]
✓ Read 2 pages                                [green check, 2.1s]
● Speaking response                           [cyan dot pulsing]
```

### Memory Recall panel (replaces GitHub context in left panel)
Shows what Burry retrieved from memory for the last query:
```
RECALLED
• "Decided JWT, no sessions" — mac-butler 3d ago
• "VPS auth issue fixed via SSH key" — 1w ago
```

### Tool indicator pills (top bar, appear dynamically)
Small animated pills between state pill and mode buttons:
`🌐 BROWSING` `💾 READING` `⚡ EXECUTING` `👁 SEEING`
Each fades in when tool fires, fades out when done.

### Orb 5th state — EXECUTING
When tool calls are running: nodes orbit fast but stay on sphere surface,
edges flash bright white, ring color shifts amber, waveform shows a
rapid sine sweep. Transitions back to SPEAKING when tools complete.

---

## Mood Engine fix (fast win)

`get_mood()` recalculates from scratch every call. Feels random.

```python
# voice/mood_engine.py
import json, time, pathlib

MOOD_STATE_PATH = pathlib.Path("memory/mood_state.json")

def load_mood_state():
    if MOOD_STATE_PATH.exists():
        return json.loads(MOOD_STATE_PATH.read_text())
    return {"mood": "focused", "set_at": time.time(), "reason": "default"}

def save_mood(mood: str, reason: str):
    MOOD_STATE_PATH.write_text(json.dumps({
        "mood": mood, "set_at": time.time(), "reason": reason
    }))

def get_mood() -> str:
    state = load_mood_state()
    age = time.time() - state["set_at"]
    # Decay toward "focused" after 30 minutes without negative signals
    if age > 1800 and state["mood"] in ["blunt", "urgent"]:
        save_mood("focused", "decay")
        return "focused"
    return state["mood"]
```

---

## Implementation Order — Do Exactly This

**Week 1 — Core intelligence:**
1. FIX 1: Feed turns into planner prompt — 30 min
2. FIX 4: Bridge mac_activity → runtime_state — 20 min
3. FIX 3: Swap models to gemma4, re-enable heartbeat/bugfinder — 1 hour
4. FIX 7: Clap pre-warming — 15 min
5. FIX 2: Wire nomic-embed-text to search_sessions — 2 hours

**Week 2 — Infrastructure:**
6. FIX 5: WebSocket push — 3 hours
7. FIX 6: Async agent fan-out — 2 hours
8. FIX 8: Native tool calling schema — 4 hours

**Week 3 — New capabilities:**
9. FIX 9: Playwright browsing agent — 3 hours
10. FIX 10: Screenshot vision — 2 hours

**Frontend — parallel to Week 2:**
- Live tool stream panel
- Memory recall panel
- Tool indicator pills in topbar
- EXECUTING orb state
- Mood engine persistence

---

## What Burry Sounds Like After All This

**Before:**
> You: "what should I work on?"
> Burry: reads PLAN.md → "Work on the task system"
> [8 seconds of silence while news agent blocks]

**After:**
> You: "what should I work on?"
> Burry instantly: [recalls last 5 turns + semantic memory search + mac context]
> "Last time we spoke you were fixing the VPS auth issue — that's resolved.
>  mac-butler task system has been blocked 4 days. I found your note about
>  the ChromaDB import conflict. I pulled the fix while you were talking —
>  it's a Python 3.11 path issue, one line change. Want me to apply it?"
> [HUD shows: ✓ recall_memory 0.3s · ✓ browse_web 1.8s · ✓ read_file 0.1s]