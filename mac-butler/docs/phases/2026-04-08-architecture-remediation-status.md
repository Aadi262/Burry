# Mac Butler Architecture Remediation Status

Last updated: 2026-04-08
Current phase: Phase 3 - Lightweight LLM Lane
Last completed phase: Phase 2 - Quick Wins
Next verification gate: `scripts/run_architecture_audit.sh`

## Phase Status

| Phase | Name | Status | Exit Gate |
| --- | --- | --- | --- |
| 1 | Audit Harness and Baseline Verification | Completed | Files, plan notebook, runbook, and audit script exist |
| 2 | Quick Wins | Completed | Hot-path latency and churn regressions are reduced |
| 3 | Lightweight LLM Lane | Pending | Unknown or question path no longer defaults to AgentScope |
| 4 | Unified Memory Bus | Pending | `_record()` no longer fans out into fragmented immediate writes |
| 5 | Split `butler.py` | Pending | Routing and orchestration are separated into testable modules |
| 6 | Frontend and Telemetry Modernization | Pending | Dashboard becomes event-driven and operationally honest |

## Next Actions

- Start Phase 3 with a single-call Smart Reply path for unknown and question turns before AgentScope.
- Clean up the remaining raw `OLLAMA_FALLBACK or OLLAMA_MODEL` default paths while Phase 3 is open.
- Run `scripts/run_architecture_audit.sh` and save the fresh report under `docs/audits/reports/`.
- Update this file, the roadmap, and `memory/plan_notebook.json` immediately after each completed phase.

## Blockers

- Unknown-intent path in `butler.py` still escalates too quickly into slow brain flows.
- `memory/store.py` and related recall paths still pay embedding or model-swap costs on the live path.
- `runtime/telemetry.py` and `_record()` still create too much JSON and disk churn.
- `butler_config.py`, `brain/agentscope_backbone.py`, and related docs still contain model drift.
- `ollama list` can crash with an MLX-backed macOS exception on this host; the audit script captures it as a non-fatal environment issue.

## Session Log

### 2026-04-08

- Completed Phase 1 planning and handoff setup.
- Added roadmap, status tracker, runbook, next-session handoff JSON, audit script, and plan notebook seed.
- Completed Phase 2 quick wins.
- Verified that route reuse, context TTL locking, static embedding dimensions, agent model unload removal, and research dispatch dedupe were already live in the codebase.
- Reduced the dashboard SSE polling interval to 500ms, removed a stale agent-runner import, and added a dedicated Phase 2 regression suite.
- Verification passed: `283` targeted tests green across Phase 2, lane, dashboard, runtime, agent, and pipeline suites.
- Refreshed audit artifact: `docs/audits/reports/architecture-audit-2026-04-08T03-15-30.md`.
