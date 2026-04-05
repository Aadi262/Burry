# Mac Butler

Mac Butler is a local operator runtime for macOS.

It reads machine context, knows active projects, routes work across local models, runs safe actions,
speaks through a local voice, and writes execution results back into memory.

No cloud dependency is required for the core system. The main runtime is built to stay local-first.

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
- dark dashboard with project cards and next actions

### Operator Runtime

- deterministic intent router for common commands
- local planner + response flow
- safe executor for apps, folders, commands, notes, reminders, URLs, SSH, and music
- project-aware `what should i do next`
- startup briefing with optional daily intelligence block
- structured execution results written back into memory

### Live Intelligence

- Hacker News agent using the public Firebase API
- Reddit agent using public subreddit JSON feeds
- GitHub trending agent using free public trending data
- market pulse agent aggregating free signals across multiple sources
- graceful fallback when local SearXNG is down

### Voice

- Kokoro local neural TTS on Apple Silicon
- safe macOS `say` fallback
- clap trigger and keyboard trigger paths

## Current Model Shape

These are the main active roles in the current Butler system:

| Role | Model |
| --- | --- |
| Voice | `phi4-mini:latest` |
| Planning | `qwen2.5-coder:14b` |
| Review / Search / Market | `deepseek-r1:14b` |
| Hacker News / Reddit / Trending | `phi4-mini:latest` |
| Coding / GitHub / VPS | `qwen2.5-coder:14b` |

Other configured fallbacks exist in [`butler_config.py`](butler_config.py).

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
- `save note ...`

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
venv/bin/python projects/open_project.py adpilot
venv/bin/python trigger.py --clap
```

## Configuration

Important runtime knobs live in [`butler_config.py`](butler_config.py).

Relevant examples:

```python
OLLAMA_MODEL = "qwen2.5:14b"
TTS_ENGINE = "kokoro"
TTS_VOICE = "af_bella"
VOICE_INPUT_MODEL = "mlx-community/whisper-tiny"
DAILY_INTEL_ENABLED = False
```

### Obsidian

If you want Butler to read and write to Obsidian, set `OBSIDIAN_VAULT_NAME` correctly.

### VPS

If you want infrastructure checks and SSH helpers, configure `VPS_HOSTS` and local secrets.

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
