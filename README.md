<p align="center">
  <br />
  <code style="font-size:3em; letter-spacing:0.3em;">
  ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗   ██╗
  ██╔══██╗██║   ██║██╔══██╗██╔══██╗╚██╗ ██╔╝
  ██████╔╝██║   ██║██████╔╝██████╔╝ ╚████╔╝ 
  ██╔══██╗██║   ██║██╔══██╗██╔══██╗  ╚██╔╝  
  ██████╔╝╚██████╔╝██║  ██║██║  ██║   ██║   
  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝  
  </code>
  <br /><br />
  <strong>Local AI operator for your Mac. Voice-activated. Memory-backed. Fully in control.</strong>
  <br /><br />
  <img src="https://img.shields.io/badge/platform-macOS-000000?style=flat-square&logo=apple&logoColor=white" />
  <img src="https://img.shields.io/badge/runtime-Python%203.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/LLM-Ollama%20local-blueviolet?style=flat-square" />
  <img src="https://img.shields.io/badge/privacy-fully%20local-00c853?style=flat-square" />
  <img src="https://img.shields.io/badge/voice-Whisper%20%2B%20EdgeTTS-orange?style=flat-square" />
  <img src="https://img.shields.io/badge/status-active-brightgreen?style=flat-square" />
  <br /><br />
  <a href="#what-burry-is">What It Is</a> ·
  <a href="#how-it-works">How It Works</a> ·
  <a href="#why-burry">Why Burry</a> ·
  <a href="#features">Features</a> ·
  <a href="#mac-control-surface">Mac Control</a> ·
  <a href="#model-routing">Model Routing</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#roadmap">Roadmap</a>
</p>

---

## What Burry Is

Burry is not a chatbot. It is not a wrapper around an API. It is not Siri.

Burry is an **AI operator** — a local system that runs on your Mac, knows your active projects, listens for your voice, and actually executes work: opens things, commits code, controls apps, plays music, runs shell commands, pings your VPS, sends messages, and writes results back into persistent memory.

Everything runs **locally**. Your code never leaves your machine. No subscription required for the core runtime.

```
You say something  →  Burry understands it  →  Burry does it  →  Burry remembers it
```

The HUD shows what your Mac is actually doing — open apps, active project, running tools, ambient intelligence — in real time, as a live operator dashboard.

---

## How It Works

### The Pipeline

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            TRIGGER                                          │
│           double clap  ·  wake word ("hey Burry")  ·  HUD input            │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    STT (Whisper)     │  MLX on Apple Silicon
                    │  transcribes audio  │  faster-whisper fallback
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Intent Router     │  deterministic — no LLM on hot path
                    │  routes command     │  100+ patterns matched instantly
                    └──────┬──────┬───────┘
                           │      │
              ┌────────────▼┐    ┌▼─────────────────┐
              │  Executor   │    │   Specialist LLM  │
              │  (direct)   │    │      Agent        │
              │  no LLM     │    │  search / code /  │
              │  needed     │    │  market / memory  │
              └────────────┬┘    └┬─────────────────-┘
                           │      │
                    ┌──────▼──────▼──────┐
                    │   Safe Executor    │  AppleScript · shell · SSH · API
                    │   runs the action  │  confirmation gating on risky ops
                    └──────────┬─────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Memory Write-Back │  session JSONL · project files
                    │   + TTS Response    │  Edge TTS / Kokoro / say fallback
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Live HUD Update   │  WebSocket push to browser HUD
                    └─────────────────────┘
```

### Background Intelligence

While you work, four daemons run silently in parallel:

| Daemon | What It Does | Interval |
|---|---|---|
| **Heartbeat (KAIROS)** | Monitors work context, suggests next steps, detects stuck state | 5 min |
| **Bug Hunter** | Scans active project for errors and regressions | 20 min |
| **Ambient** | Reads machine state, open apps, active editor, recent git activity | 30 s |
| **Mac Watcher** | Tracks frontmost app, open windows, workspace path | 30 s |

### Memory Layers

```
Layer 0  ·  MEMORY.md index          fast lookup, session-persistent
Layer 1  ·  per-project .md files    project context, blockers, last state
Layer 2  ·  session JSONL            every heard/spoken/intent/tool event
Layer 3  ·  dependency graph         cross-project relationships (blocked_by, depends_on)
Layer 4  ·  runtime_state.json       live state for HUD, updated every 350 ms
```

---

## Why Burry

Every AI assistant on the market has the same fundamental problem: it does not know what you are actually doing.

| Capability | Burry | Siri | Copilot | Raycast AI | ChatGPT Desktop |
|---|:---:|:---:|:---:|:---:|:---:|
| Fully local (no cloud required) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Knows your active projects | ✅ | ❌ | ❌ | ❌ | ❌ |
| Persistent developer memory | ✅ | ❌ | ❌ | ❌ | ❌ |
| Voice-first (Whisper, not browser) | ✅ | ✅ | ❌ | ❌ | ✅ |
| Wake word activation | ✅ | ✅ | ❌ | ❌ | ❌ |
| Live operator HUD | ✅ | ❌ | ❌ | ❌ | ❌ |
| Full Mac window/app control | ✅ | ✅ | ❌ | partial | ❌ |
| Chrome tab management | ✅ | ❌ | ❌ | ❌ | ❌ |
| Git-aware (commit, status, diff) | ✅ | ❌ | ❌ | ❌ | ❌ |
| SSH / VPS control | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-model routing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Background intelligence daemons | ✅ | ❌ | ❌ | ❌ | ❌ |
| Obsidian integration | ✅ | ❌ | ❌ | ❌ | ❌ |
| Privacy (your data stays local) | ✅ | ❌ | ❌ | ❌ | ❌ |

**Siri** is deeper in the OS (volume, brightness, Focus modes) but has no developer context, no project memory, no code awareness, and no HUD. It does not know what you are building.

**Copilot** reasons well inside Office apps and has strong cloud models, but it is cloud-only, has no Mac control, and has no voice-first path outside of Windows.

**Raycast AI** is fast and extensible, but it is not voice-first, has no persistent project memory, and does not run local models.

**ChatGPT Desktop** can see your screen on request, but it is cloud-only, has no Mac control, no background daemons, and no project context.

Burry is the only system that combines **local LLM reasoning + persistent developer memory + background awareness + full Mac control + visual HUD** in one runtime.

---

## Features

### Voice & Activation

- **Double-clap trigger** — two claps from across the room activates listening
- **Wake word** — "hey Burry" via openWakeWord
- **HUD command dock** — type or speak from the browser HUD
- **Whisper STT** — `mlx-community/whisper-base-mlx` on Apple Silicon, `faster-whisper` fallback
- **Edge TTS** — `en-US-AvaMultilingualNeural` neural voice, Kokoro local fallback, `say` emergency fallback
- **Follow-up detection** — multi-turn conversation with 4-second follow-up window

### Mac Control (via AppleScript + subprocess)

- Open, focus, minimize, hide any app
- Chrome: open tab, close tab, focus tab by title
- Spotify: play, pause, next, prev, volume, now playing, search and play
- Send email via Mail.app
- Send iMessage via Messages.app
- Send WhatsApp message via WhatsApp Desktop
- Desktop notifications
- Set reminders via macOS Reminders
- SSH into VPS, run remote commands
- Run safe shell commands in any project directory
- Open files and folders in Finder
- Open URLs in Chrome

### Developer Intelligence

- `open mac-butler` — opens the right editor with the right workspace
- `git status` / `git commit` — staged diff → LLM generates message → commits
- `what should I do next` — reads project state, blockers, tasks, and replies with a prioritized answer
- `check vps` — SSH health check, CPU/memory/disk
- `run tests` — executes test suite, speaks summary of pass/fail
- `search for X` — SearXNG local search → Exa fallback → summarized spoken response

### Live Intelligence (always-on agents)

- **Hacker News** — Firebase API, top stories summarized locally
- **Reddit** — public subreddit feeds, signal extraction
- **GitHub Trending** — free trending data, tech radar awareness
- **Market Pulse** — aggregates free signals, crypto + tech sentiment
- **AI News** — daily AI research and product news digest

### Project OS

- `projects/projects.json` is the source of truth for all tracked projects
- Per-project: name, status, blockers, next steps, health score, verification
- `open_project` fuzzy match → editor detection → workspace open
- GitHub sync pulls public metadata
- Project memory written back after every execution

### HUD (Live Operator Dashboard)

- **Topbar**: state pill (idle / listening / thinking / speaking), active tool pills
- **Left rail**: open Mac apps with status dots, workspace info, ambient bullets
- **Center stage**: animated 3D orb (state-aware color) + project dependency graph
- **Right rail**: live events stream, pending tasks, memory recall
- **Command dock**: voice mic button + text input → full butler pipeline
- **WebSocket push** — HUD updates on every state change, not on a timer
- **Offline banner** — shows when daemon is not running

### Memory

- Every command heard, every intent routed, every tool call, every response spoken → written to session JSONL
- Project memory updated after execution — Burry knows what it did last time
- Layered memory with semantic search across sessions
- Cross-project dependency graph (`depends_on`, `blocked_by`, `shares_resource`)
- Learner analyzes sessions and surfaces behavioral patterns

---

## Mac Control Surface

A full list of what Burry can execute on your machine:

```
App Control          open · focus · minimize · hide · quit
Window Management    focus window · minimize window · hide process
Chrome               open tab · close tab · focus tab by title
Spotify              play · pause · next · prev · volume · search · now playing
Mail                 compose and send email
Messages             send iMessage
WhatsApp             send WhatsApp message (requires WhatsApp Desktop)
Obsidian             create note · append to note · daily note write
Reminders            set reminder at time offset
Notifications        macOS banner notification
Shell                safe command execution in project directories
Git                  status · staged diff · commit with generated message
SSH                  open session · run remote command · health check
Files                write file · append file · open in Finder · open URL
Agents               delegate to search / code / market / memory specialist
Screenshot           capture screen and describe with vision model
```

---

## Model Routing

Burry routes different tasks to different models. No single model handles everything.

| Role | Primary Model | Fallback Chain |
|---|---|---|
| Voice / Fast | `gemma4:e4b` | `phi4-mini` → `llama3.2:3b` → `deepseek-r1:7b` |
| Planning | `gemma4:e4b` | `deepseek-r1:14b` → `qwen2.5-coder:14b` → `deepseek-r1:7b` |
| Review / Search | `deepseek-r1:14b` | `glm-4.7-flash` → `deepseek-r1:7b` |
| Coding / GitHub | `deepseek-r1:14b` | `qwen2.5-coder:14b` → `deepseek-coder:6.7b` |
| Vision | `gemma4:e4b` | `llama3.2-vision` → planning chain |
| HN / Reddit / Trending | `gemma4:e4b` | `phi4-mini` → `llama3.2:3b` |
| VPS Agent | `deepseek-r1:14b` | `qwen2.5-coder:14b` → `deepseek-coder:6.7b` |
| Bug Hunter | `gemma4:e4b` | `phi4-mini` → `deepseek-r1:7b` |

VPS offloading is also supported: set `USE_VPS_OLLAMA = True` in `butler_config.py` to run heavier models on a remote machine and stream results back locally.

---

## Quick Start

**Requirements:** macOS (Apple Silicon recommended), Python 3.11+, [Ollama](https://ollama.ai) running locally with at least one model pulled.

```bash
# 1. Clone and set up
cd mac-butler
chmod +x setup.sh
./setup.sh
source venv/bin/activate

# 2. (Optional) Start local search
bash scripts/start_searxng.sh

# 3. Start the HUD server
venv/bin/python projects/dashboard.py

# 4. Run Butler
venv/bin/python butler.py

# 5. Or run in test mode (no mic, no TTS)
venv/bin/python butler.py --test --command "what should I do next"
```

**Open the HUD:** `http://127.0.0.1:3333` in any browser.

### Useful Commands

```bash
# Project flows
venv/bin/python projects/open_project.py mac-butler
venv/bin/python projects/github_sync.py

# Test suite
venv/bin/python -m unittest discover -s tests -v

# Smoke checks
venv/bin/python butler.py --test --command "what's happening in AI today"
venv/bin/python butler.py --test --command "trending repos"
venv/bin/python butler.py --test --command "check vps"
```

### Configuration

All knobs live in [`mac-butler/butler_config.py`](mac-butler/butler_config.py):

```python
OLLAMA_MODEL          = "deepseek-r1:14b"   # primary planning model
TTS_ENGINE            = "edge"              # "edge" | "kokoro" | "say"
EDGE_TTS_VOICE        = "en-US-AvaMultilingualNeural"
VOICE_INPUT_MODEL     = "mlx-community/whisper-base-mlx"
HEARTBEAT_ENABLED     = True
HEARTBEAT_INTERVAL_MINUTES = 5
BUG_HUNTER_ENABLED    = True
REQUIRE_CONFIRMATION_FOR_PUSH = True
```

Secrets (API keys, VPS passwords) go in [`mac-butler/butler_secrets/local_secrets.json`](mac-butler/butler_secrets/local_secrets.json) — not in config.

### Permissions

| Feature | Permission Needed |
|---|---|
| Clap trigger / voice input | Microphone access for Terminal |
| Keyboard shortcut trigger | Accessibility access for Terminal |
| AppleScript app control | Automation access per app |
| WhatsApp / keystroke actions | Accessibility access for Terminal |

---

## Architecture

```
Burry/
├── mac-butler/
│   ├── butler.py              main orchestrator — pipeline entry point
│   ├── butler_config.py       all runtime configuration and model chains
│   │
│   ├── intents/
│   │   └── router.py          deterministic intent router — no LLM on hot path
│   │
│   ├── executor/
│   │   └── engine.py          safe action executor — AppleScript, shell, SSH, API
│   │
│   ├── brain/
│   │   ├── tools.py           LLM tool-calling schema
│   │   ├── ollama_client.py   model client with fallback chain
│   │   ├── query_analyzer.py  query type classification
│   │   └── mood_engine.py     personality and response tone
│   │
│   ├── agents/
│   │   ├── runner.py          specialist agent orchestration
│   │   └── vision.py          screenshot + visual understanding
│   │
│   ├── daemon/
│   │   ├── heartbeat.py       KAIROS proactive intelligence loop
│   │   ├── wake_word.py       keyword activation daemon
│   │   ├── bug_hunter.py      background code error detector
│   │   ├── clap_detector.py   double-clap microphone trigger
│   │   └── ambient.py         machine state + context refresh
│   │
│   ├── context/
│   │   ├── mac_activity.py    open apps, frontmost window, workspace detection
│   │   ├── vscode_context.py  active editor, open files, workspace path
│   │   ├── obsidian_context.py recent notes and daily page
│   │   ├── tasks_context.py   active tasks from task store
│   │   ├── vps_context.py     VPS health via SSH
│   │   └── mcp_context.py     MCP server tool context injection
│   │
│   ├── memory/
│   │   ├── layered.py         layered memory read/write (MEMORY.md + project + session)
│   │   ├── store.py           project execution record and session history
│   │   ├── learner.py         behavioral pattern learning from sessions
│   │   ├── graph.py           cross-project dependency graph
│   │   └── layers/
│   │       ├── MEMORY.md      fast-lookup session index
│   │       ├── graph.json     project dependency edges
│   │       ├── projects/      per-project memory files
│   │       └── sessions/      per-day JSONL event logs
│   │
│   ├── projects/
│   │   ├── dashboard.py       HTTP server + SSE + WebSocket + API endpoints
│   │   ├── project_store.py   project registry with derived state
│   │   ├── open_project.py    fuzzy project open with editor fallback
│   │   ├── github_sync.py     public GitHub metadata sync
│   │   └── frontend/
│   │       ├── index.html     HUD shell and layout
│   │       ├── style.css      design system — dark, state-aware colors
│   │       └── modules/
│   │           ├── orb.js     Three.js animated state orb
│   │           ├── graph.js   project dependency force graph
│   │           ├── stream.js  WebSocket connection and state dispatch
│   │           ├── panels.js  DOM update functions for all panels
│   │           ├── mac-activity.js  open app list with category badges
│   │           ├── events.js  live events stream rendering
│   │           └── commands.js  command dock and keyboard shortcuts
│   │
│   ├── voice/
│   │   ├── stt.py             Whisper MLX + faster-whisper STT
│   │   └── tts.py             Edge TTS + Kokoro + say fallback
│   │
│   ├── tasks/                 task store with project-aware priority
│   ├── mcp/                   MCP client for Brave + GitHub servers
│   ├── identity/              personality profile and loader
│   ├── butler_secrets/        local secrets loader (not committed)
│   └── tests/                 regression suite
│
├── assets/
│   ├── burry-banner.svg
│   ├── dashboard-preview.svg
│   └── butler-session.svg
│
└── Butler Vault/              local operating notes and private memory
```

---

## Example Commands

```
# Open a project
"open mac-butler"
"open email-infra in cursor"

# Developer workflows
"what should I do next"
"git status"
"commit my changes"
"run the tests"
"check the VPS"

# Mac control
"focus Chrome"
"minimize Slack"
"open a new tab at github.com"
"close the Linear tab"
"pause music"
"play something chill"
"next track"

# Intelligence
"what's happening in AI today"
"what's on Hacker News"
"trending repos this week"
"what's the market doing"

# Utility
"save a note about the auth refactor"
"remind me in 30 minutes to review the PR"
"send an email to aditya@example.com about the deploy"
"take a screenshot and describe what's open"

# Memory
"what did I work on yesterday"
"what do you know about Adpilot"
"what's blocking email-infra"
```

---

## Roadmap

### Now
- Full Mac system control (volume, brightness, Focus modes)
- Shell output spoken back as voice summary
- `git diff` → LLM commit message suggestion
- Calendar awareness in heartbeat ("meeting in 20 minutes")
- WebSocket fully replacing SSE for HUD updates

### Next
- iOS companion app — read-only HUD mirror on iPhone
- Wake word training for custom phrase
- Auto-populate dependency graph from session co-occurrence
- Per-project context auto-injected on `open_project`
- VPS metrics streamed live to HUD

### Later
- Native Swift/SwiftUI wrapper (removes browser dependency for HUD)
- Windows port (PowerShell + Win32 API replaces AppleScript)
- Team memory sync via self-hosted VPS
- Plugin marketplace for community executor actions
- Screen understanding — continuous visual context, not just on-demand screenshots

---

## Status

```
Core pipeline         ✅ working
Intent router         ✅ working
Executor              ✅ working
Voice (STT + TTS)     ✅ working
HUD                   ✅ working
Background daemons    ✅ working
Memory system         ✅ working
Project OS            ✅ working
Multi-model routing   ✅ working
Live intelligence     ✅ working
Test suite            ✅ green
```

---

<p align="center">
  Built for developers who want their machine to actually work for them.
  <br />
  Local. Private. Yours.
</p>
