# Mac Butler

Mac Butler is a local operator runtime for macOS.

It reads machine context, knows active projects, routes work across local models, runs safe actions,
speaks through a local voice, and writes execution results back into memory.

The runtime stays local-first, but it can now route selected LLM, TTS, and STT roles through NVIDIA when configured.
Local degraded mode still works without cloud credentials.

## What Butler Is

Butler is not meant to be a generic assistant shell.

The goal is to make a local operator that can answer practical questions while you work:

- What should I do next?
- Which project am I actually in?
- What is blocked?
- What should open when I say "open adpilot"?
- Which model should handle this request?
- What happened after the action ran?

That means the product is built around:

- project intelligence
- deterministic routing
- specialist agents
- execution safety
- memory write-back
- live dashboard truth

## What Works Now

### Project OS

- registry of tracked projects in `projects/projects.json`
- derived completion, blockers, next tasks, health, and verification
- fuzzy `open_project` flow with real editor fallback behavior
- GitHub sync for public repos
- direct GitHub repo-status lookup for tracked projects and `owner/repo` phrases
- dark dashboard with project cards and next actions

### Operator Runtime

- deterministic intent router for common commands
- local planner + response flow
- verification-aware executor for apps, folders, browser, terminal, files, calendar add, URLs, reminders, SSH, and music
- browser control for new tab, new window, back, refresh, and URL navigation on the resolved browser family
- filesystem routing for create/open/read/write/find/list, move/copy/rename/delete, and zip flows on common local paths
- system-control routing for common volume, mute, brightness, screenshot, lock-screen, sleep, show-desktop, dark-mode, DND, and battery or wifi phrases
- calendar read for today, tomorrow, next event, and this-week phrasing with truthful host-permission fallback
- current-news lookup with search-first plus Google News RSS fallback when search backends are thin, plus repeated-query caching and snippet-first enrichment to cut avoidable live fetches
- weather lookup now uses dedicated public weather providers with `wttr.in` first and Open-Meteo fallback
- quick facts now prefer DuckDuckGo instant answers and Wikipedia summaries before falling back to generic search
- GitHub status now resolves tracked-project repos and direct `owner/repo` phrases through public API reads before MCP fallback
- page summarization and page fetch now reuse indexed page snapshots, with Jina first and direct extraction fallback when live fetch is needed
- video summarization with YouTube captions first, then `yt-dlp` / Whisper / Jina fallbacks
- project-aware `what should i do next`
- startup briefing with optional daily intelligence block
- structured execution results written back into memory
- recent turn memory and pending follow-ups now survive short restarts through a persisted `session_context.py` snapshot

### Reliability Notes

- browser, filesystem, terminal, project-open, and calendar-create actions now return verification-aware follow-ups instead of optimistic success only
- reminders now verify against the Reminders list when automation access is available
- Gmail compose and WhatsApp flows are verification-aware about what was actually opened
- Mail send and WhatsApp desktop send still use degraded-state messaging when delivery cannot be confirmed
- calendar read and calendar create now return explicit host-permission messages when Calendar automation access is unavailable instead of bubbling raw automation errors
- the background bug hunter now runs only the documented safe phase-scoped host smoke entrypoints instead of the broad default smoke path
- the live host smoke entrypoints are `venv/bin/python scripts/system_check.py --phase1-host --phase1-host-only` and `venv/bin/python scripts/system_check.py --phase3a-host --phase3a-host-only`

### Contract Surface

- dashboard and A2A HTTP surfaces now use `/api/v1/...` as the only supported public namespace
- dashboard GET responses now use a typed envelope: `{ contract_version, kind, data }`
- `GET /api/v1/capabilities` now returns the stable public capability catalog with capability IDs from `.CODEX/Capability_Map.md`
- live HUD WebSocket events now carry `event_version`, `type`, `ts`, and `data`
- legacy WebSocket `payload` is still mirrored for compatibility while the current HUD transitions fully onto `data`

### Live Intelligence

- news agent with SearXNG, DuckDuckGo, Exa, and Google News RSS fallback paths
- Hacker News agent using the public Firebase API
- Reddit agent using public subreddit JSON feeds
- GitHub trending agent using free public trending data
- market pulse agent aggregating free signals across multiple sources
- graceful fallback when local SearXNG is down

### Voice

- NVIDIA Riva multilingual TTS primary when configured
- Hindi auto voice selection for Devanagari text on the NVIDIA TTS path
- NVIDIA Riva multilingual ASR primary when configured
- Kokoro local neural TTS on Apple Silicon
- Edge and safe macOS `say` fallbacks
- local Whisper fallbacks for STT
- clap trigger and keyboard trigger paths

## Current Model Shape

These are the main active roles in the current Butler system:

| Role | Primary | Fallback |
| --- | --- |
| Intent classifier / fast voice / conversation | `nvidia::nvidia/nvidia-nemotron-nano-9b-v2` | `ollama_local::gemma4:e4b` |
| Planning / startup briefing | `nvidia::qwen/qwq-32b` | `ollama_vps::gemma4:26b` -> `ollama_local::gemma4:e4b` |
| Review / search / bug hunter | `nvidia::deepseek-ai/deepseek-r1-distill-qwen-32b` | `ollama_local::deepseek-r1:14b` |
| Coding | `nvidia::qwen/qwen2.5-coder-32b-instruct` | `ollama_vps::gemma4:26b` -> `ollama_local::deepseek-r1:14b` |
| TTS | `nvidia_riva_tts::magpie-tts-multilingual` | `kokoro` -> `edge` -> `say` |
| STT | `nvidia_riva_asr::parakeet-1.1b-rnnt-multilingual-asr` | `mlx-community/whisper-medium-mlx` -> `faster-whisper medium.en` |
| Embeddings | `nomic-embed-text` |
| VPS-only large local fallback | `gemma4:26b` |

Without `NVIDIA_API_KEY` or NVIDIA Riva Python clients, Butler drops back to the local chains above.

## Example Commands

### Project + Operator Commands

- `open adpilot`
- `open mac-butler`
- `what should i do next`
- `open dashboard`
- `git status`
- `check vps`

### Intelligence Commands

- `what's happening in AI today`
- `what's on hackernews`
- `what's reddit saying`
- `trending repos`
- `latest ai news`

### Utility Commands

- `open spotify`
- `play mockingbird`
- `pause music`
- `go back`
- `refresh this page`
- `open a new browser window`
- `open budget.xlsx`
- `what's on my desktop`
- `move resume to documents`
- `copy resume to downloads`
- `mute the system`
- `set brightness to 70`
- `turn on dark mode`
- `how much battery do i have`
- `what's my next meeting`
- `show my agenda this week`
- `summarize this article`
- `save notes from this video`
- `save note ...`
- `write a mail to vedang@gmail.com`
- `send whatsapp to vedang message ship it tonight`

## System Flow

```text
Trigger / Command
    -> Intent Router
    -> Direct Action or Specialist Agent
    -> Safe Executor
    -> Memory Write-Back
    -> Spoken / Printed Response
```

For project-aware flows, Butler also pulls from:

- editor/workspace context
- git context
- task context
- project registry + derived status
- previous session memory

## Main Components

| Path | Responsibility |
| --- | --- |
| `butler.py` | Main runtime orchestration |
| `butler_config.py` | Model, voice, and feature flags |
| `intents/router.py` | Deterministic command routing |
| `executor/engine.py` | Safe action execution |
| `agents/runner.py` | Specialist agents |
| `projects/` | Project OS, dashboard, GitHub sync, open flow |
| `memory/` | Session memory and project write-back |
| `voice/` | TTS and STT |
| `context/` | Machine, editor, git, task, and time context |
| `tests/` | Regression coverage |

## Project OS Surface

The core project intelligence layer lives in `projects/`:

- `projects.json`
  Source of truth for tracked projects

- `project_store.py`
  Loads and derives project state from local files, git signals, memory, and verification data

- `open_project.py`
  Fuzzy project open flow with editor fallback chain

- `github_sync.py`
  Public GitHub metadata sync

- `dashboard.py`
  Dashboard HTML generator and local server

This is the layer that makes Butler understand work instead of just reacting to commands.

## Quick Start

```bash
cd mac-butler
chmod +x setup.sh
./setup.sh
source venv/bin/activate
```

If you want the full local search path:

```bash
bash scripts/start_searxng.sh
```

Run Butler:

```bash
venv/bin/python butler.py
```

Test mode:

```bash
venv/bin/python butler.py --test
```

Useful direct entrypoints:

```bash
venv/bin/python projects/dashboard.py
venv/bin/python projects/github_sync.py
venv/bin/python scripts/benchmark_models.py --json --dry-run
venv/bin/python projects/open_project.py adpilot
venv/bin/python trigger.py --clap
```

## Configuration

Important runtime knobs live in [`butler_config.py`](butler_config.py).

Relevant examples:

```python
NVIDIA_API_KEY = "..."
TTS_ENGINE = "nvidia_riva_tts"
VOICE_INPUT_BACKEND = "nvidia_riva_asr"
TTS_TARGETS = [...]
STT_TARGETS = [...]
DAILY_INTEL_ENABLED = False
```

### Obsidian

If you want Butler to read and write to Obsidian, set `OBSIDIAN_VAULT_NAME` correctly.

### VPS

If you want infrastructure checks and SSH helpers, configure `VPS_HOSTS` and local secrets.

### NVIDIA

If you want the NVIDIA primary path, set `NVIDIA_API_KEY`.
For speech, install the NVIDIA Riva Python clients on the host too; otherwise Butler falls back to local TTS/STT.

### MCP

Brave Search MCP and GitHub MCP are optional. Butler can run without them, but they expand the search and GitHub surface.

## Verification

Current regression baseline:

- `venv/bin/python -m unittest discover -s tests -v`
- expected result: green suite

Useful smoke checks:

```bash
venv/bin/python butler.py --test --command "what's happening in AI today"
venv/bin/python butler.py --test --command "what's on hackernews"
venv/bin/python butler.py --test --command "trending repos"
venv/bin/python butler.py --test --command "what should i do next"
```

## Project Layout

```text
mac-butler/
├── agents/
├── brain/
├── context/
├── daemon/
├── executor/
├── identity/
├── intents/
├── mcp/
├── memory/
├── projects/
├── scripts/
├── tasks/
├── tests/
├── voice/
├── butler.py
├── butler_config.py
├── setup.sh
└── trigger.py
```

## Permissions

For keyboard mode, grant Accessibility permissions to the app that runs Butler.

For clap mode, grant Microphone access to the terminal app that runs Butler.

## Notes

- Spotify actions need the Spotify desktop app installed
- `run_command` is intentionally constrained
- project state is partly derived from local docs, so stale project docs still affect downstream truth
- local runtime JSON files change often during development and are not always meant for commit
