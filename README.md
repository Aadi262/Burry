<p align="center">
  <img src="assets/burry-banner.svg" alt="Burry banner" width="100%" />
</p>

# Burry

Burry is Aditya's operator workspace. The main system here is `mac-butler`: a local project OS for opening projects, tracking state, routing work across local models, and keeping execution memory tied to the real codebase.

## What Exists Now

- Project registry for 7 active products with one source of truth in `mac-butler/projects/projects.json`
- Runtime-derived project state from local docs, git activity, execution memory, and local live checks
- Open-project fallback chain wired into Butler and the dashboard
- GitHub sync for repo metadata and README context
- Backend-aware Ollama routing using the strongest locally installed models instead of blindly preferring the VPS
- Dashboard with completion, blockers, next tasks, health state, verification state, and one-click open actions

## Current Model Stack

These are the models Butler now picks from on this machine:

| Role | Model | Backend |
| --- | --- | --- |
| Voice | `phi4-mini:latest` | local |
| Planning | `qwen2.5-coder:14b` | local |
| Review | `deepseek-r1:14b` | local |
| Coding | `qwen2.5-coder:14b` | local |
| News/Search | `deepseek-r1:14b` | local |
| GitHub/VPS/Code agents | `qwen2.5-coder:14b` | local |

## Repo Layout

```text
Burry/
├── assets/
│   └── burry-banner.svg
├── Butler Vault/
│   └── local notes, plans, and operator memory
├── mac-butler/
│   ├── brain/
│   ├── context/
│   ├── executor/
│   ├── memory/
│   ├── projects/
│   ├── tests/
│   └── butler.py
└── README.md
```

## `mac-butler` in One Sentence

`mac-butler` is a local macOS operator that gathers context, plans actions with Ollama, executes safe actions, updates project memory, and exposes the full project system through a dashboard.

## Project OS Status

- Structured project memory write-back is live
- Multi-model routing is explicit and backend-aware
- Project health checks are derived from the real workspace
- Dashboard and project open flows are wired
- Comprehensive regression suite is passing: `92/92`

## Quick Start

```bash
cd mac-butler
./setup.sh
venv/bin/python projects/dashboard.py
venv/bin/python butler.py --test
```

Useful checks:

```bash
cd mac-butler
venv/bin/python projects/github_sync.py
venv/bin/python projects/open_project.py adpilot
venv/bin/python -m unittest tests.test_comprehensive -v
```

## Why This Repo Exists

The goal is not just another assistant shell. Burry is meant to become an actual operator layer:

- know the real project state
- open the right workspace fast
- store execution results back into memory
- route the right work to the right model
- keep the dashboard honest

## Notes

- `Butler Vault/` contains working notes and is part of the workspace story, but `mac-butler/` is the codebase that drives the system
- `Butler Vault/` and `.claude/` stay local and are intentionally not tracked in the public repo
- generated local memory, secrets, and runtime artifacts are ignored at the repo root
- the repo banner is a local SVG asset so the GitHub page renders cleanly without extra setup
