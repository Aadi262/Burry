# Burry

Burry is a local-first operator repo centered on `mac-butler`, a macOS agent runtime that listens, routes work, runs actions, verifies side effects, and writes execution results back into memory.

This top-level README is intentionally short. The old version had stale feature claims, stale model routing, and stale roadmap items.

## Source Of Truth

- Runtime overview: [`mac-butler/README.md`](mac-butler/README.md)
- Session rules: [`mac-butler/.CODEX/Codex.md`](mac-butler/.CODEX/Codex.md)
- Stable phase plan: [`mac-butler/docs/phases/PHASE.md`](mac-butler/docs/phases/PHASE.md)
- Live phase status: [`mac-butler/docs/phases/PHASE_PROGRESS.md`](mac-butler/docs/phases/PHASE_PROGRESS.md)

## Current Phase

The repo is in `Phase 1 - Hardening`.

Current focus:

- deterministic routing
- typed execution boundaries
- verification-aware side effects
- truthful narration
- runtime boundary cleanup
- regression coverage before new breadth

## What Is Safe To Claim Right Now

- hot path routing is pinned as `pending -> instant -> skills -> classifier -> lane`
- the executor now attaches verification metadata for major side-effect families
- direct action narration prefers verified outcomes over optimistic success text
- toolkit wrappers now surface verification-aware result text
- touched core modules publish HUD events through runtime telemetry helpers instead of direct dashboard imports

## What Is Still In Progress

- host-machine smoke validation for calendar read, Mail delivery, WhatsApp delivery, browser, terminal, and filesystem flows
- remaining exact phrase regressions from the Phase 1 backlog
- capability-map reconciliation against the now-verified runtime behavior

## Repo Layout

- `mac-butler/`
  Main runtime, tests, docs, memory, dashboard, and supporting modules.
- `assets/`
  Shared visual assets used by repo docs and previews.

## Quick Start

```bash
cd mac-butler
chmod +x setup.sh
./setup.sh
source venv/bin/activate
venv/bin/python butler.py
```

Optional local search:

```bash
bash scripts/start_searxng.sh
```

Targeted regression example:

```bash
venv/bin/pytest tests/test_executor.py tests/test_butler_pipeline.py
```
