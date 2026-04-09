# Mac Butler Architecture Remediation Roadmap

Last updated: 2026-04-08
Owner: Aditya + Codex
Status: Active

**Total: 2 of 6 phases complete (33%)**

## Goal

Make `mac-butler` ready for reliable end-to-end testing by removing live-path latency, stale model routing, memory fragmentation, dashboard I/O churn, and observability gaps.

## Current Bottlenecks

- Unknown intents still fall into the slow Brain path and can cascade into multiple sequential LLM calls.
- Semantic memory recall still relies on synchronous embedding/model swapping.
- `build_structured_context()` gathers more sources than the live voice path can afford.
- `_record()` still fans out into too many JSON writes across fragmented stores.
- The dashboard still depends on polling for SSE and watcher updates, even after the Phase 2 throttle reduction.
- `butler.py` remains a God object and blocks isolated optimization.
- Model config and a few default code paths still reference uninstalled fallbacks.

## What to do RIGHT NOW (in order of impact)

1. Phase 3: add the lightweight LLM lane so unknown and question turns stop defaulting to AgentScope.
2. Decide whether `gemma4:26b` should own local planning/review/coding or stay VPS-only before model cleanup.
3. Keep [2026-04-08-architecture-remediation-status.md](/Users/adityatiwari/Burry/mac-butler/docs/phases/2026-04-08-architecture-remediation-status.md) and [plan_notebook.json](/Users/adityatiwari/Burry/mac-butler/memory/plan_notebook.json) updated after each completed phase.
4. Run `scripts/run_architecture_audit.sh` after each phase and save the fresh report.

## Known Risks

- Quick local wins can regress voice latency if the raw `_raw_llm()` fallback path is not cleaned at the same time.
- Memory consolidation will touch multiple stores and can break recall unless the migration is staged.
- Splitting `butler.py` will change imports across the codebase and needs a stable regression gate first.
- Frontend and dashboard changes can hide state regressions if observability lands after the UI rewrite.

## Open Questions

- Should `gemma4:26b` become the preferred local planning/review model, or remain reserved for VPS or offload-only work?
- Should the Lightweight LLM lane ship before memory unification, or after the quick wins stabilize?
- Should the native HUD remain a first-class surface, or should the browser dashboard become the primary operator view?

## Phase 1 - Audit Harness and Baseline Verification

Status: Completed on 2026-04-08.

Scope:

- Capture the architectural audit in durable repo files.
- Create a repeatable audit runbook and report generator.
- Seed an active phase tracker for the next session.

Done:

- Added this roadmap.
- Added a phase tracker, runbook, next-session handoff, and audit script.
- Seeded `memory/plan_notebook.json`.
- Updated `projects/projects.json` so `mac-butler` points at the new roadmap files.

Exit Criteria:

- The next session can see the active phase, bottlenecks, blockers, audit commands, and file list without recreating context.

## Phase 2 - Quick Wins

Status: Completed on 2026-04-08.

Focus:

- Cache the early `route()` result and reuse it on the agent lane.
- Increase the context cache TTL and make stale rebuilds less frequent.
- Reduce dashboard operator polling frequency or remove it from the hot path.
- Remove the agent model unload carousel in `agents/runner.py`.
- Replace runtime embedding dimension probing with a static value.
- Deduplicate the copied `research` dispatch logic in `butler.py`.

Completed:

- Verified `handle_input()` already reuses the early `route()` result instead of re-routing on the normal agent path.
- Verified `_get_cached_context()` already uses a 120-second TTL and rebuilds under the cache lock.
- Verified `memory/knowledge_base.py` already uses a static 768-dimension embedding size.
- Verified `agents/runner.py` already removed the model unload carousel and now leaves Ollama eviction to the runtime.
- Verified `butler.py` already centralizes research dispatch via `_dispatch_research()`.
- Reduced the dashboard SSE stream cadence to 500ms so it matches the less aggressive operator watcher cadence.
- Added `tests/test_architecture_phase2.py` and wired it into `scripts/run_architecture_audit.sh` so the quick wins stay pinned by regression coverage.

Target Files:

- `butler.py`
- `projects/dashboard.py`
- `agents/runner.py`
- `memory/knowledge_base.py`
- `trigger.py` if the cache change touches wake flow
- `tests/test_architecture_phase2.py`
- `scripts/run_architecture_audit.sh`

Verification:

- Run `scripts/run_architecture_audit.sh`.
- Run targeted suites for routing, dashboard, executor, telemetry, and project store.
- Confirm the quick-win regression suite stays green.
- Compare before or after latency for `unknown`, `news`, and `memory recall` paths.

## Phase 3 - Lightweight LLM Lane

Status: Pending.

Focus:

- Add a single-call Smart Reply lane between Instant and Brain.
- Keep tool calling and AgentScope off the path unless the user explicitly asks for research or tools.
- Tighten unknown and question routing so normal conversation does not enter the ReAct loop by default.

Target Files:

- `butler.py`
- `brain/ollama_client.py`
- `intents/router.py`

Verification:

- Unknown and question utterances resolve in one model call when no tools are required.
- Brain-only fallback triggers only on explicit research or clear failure.

## Phase 4 - Unified Memory Bus

Status: Pending.

Focus:

- Create a single write interface for command, session, and memory recording.
- Batch or debounce writes instead of writing every JSON store on every command.
- Start a graph-style memory layer with one recall API.

Target Files:

- `memory/bus.py`
- `memory/store.py`
- `memory/long_term.py`
- `memory/layered.py`
- `memory/graph.py`
- `butler.py`

Verification:

- Count file writes per command before and after.
- Confirm recall quality does not regress on project, auth, and session-memory prompts.

## Phase 5 - Split butler.py

Status: Pending.

Focus:

- Extract routing, orchestration, execution coordination, recording, and speech into separate pipeline modules.
- Leave `butler.py` as a thin facade.

Target Files:

- `pipeline/routing.py`
- `pipeline/llm_orchestrator.py`
- `pipeline/action_runner.py`
- `pipeline/recorder.py`
- `pipeline/speech.py`
- `butler.py`

Verification:

- Existing lane tests still pass.
- No circular import regressions.
- CLI smoke checks still work.

## Phase 6 - Frontend and Telemetry Modernization

Status: Pending.

Focus:

- Replace heavy polling with event-driven HUD updates.
- Add structured logging and error counters.
- Make the dashboard show real operator state and failure modes.

Target Files:

- `projects/dashboard.py`
- `projects/frontend/`
- `runtime/telemetry.py`
- `runtime/tracing.py`
- `runtime/log_store.py`

Verification:

- Dashboard CPU and disk churn drops measurably.
- `/api/metrics`, `/api/logs`, and `/api/traces` reflect live activity.
- UI shows stale, offline, and error states explicitly.

## After This Phase

- Update [2026-04-08-architecture-remediation-status.md](/Users/adityatiwari/Burry/mac-butler/docs/phases/2026-04-08-architecture-remediation-status.md).
- Update [plan_notebook.json](/Users/adityatiwari/Burry/mac-butler/memory/plan_notebook.json).
- Refresh [2026-04-08-next-session-handoff.json](/Users/adityatiwari/Burry/mac-butler/docs/audits/2026-04-08-next-session-handoff.json).
- Run `scripts/run_architecture_audit.sh`.
