# Burry Phase Progress

Last updated: 2026-04-18
Status: Active
Read after: `docs/phases/PHASE.md`

This file tracks live progress against the roadmap in `PHASE.md`.
`PHASE.md` defines what the phases are.
`PHASE_PROGRESS.md` tracks where the work stands right now.

## Current State

- Current phase: `Phase 3 - Feature Completion`
- Current focus: `Phase 3B - Retrieval and Knowledge Quality`, with indexed page retrieval plus dedicated weather, quick-fact, and GitHub-status retrieval now landed on top of the closed `Phase 3A` action surface, retrieval latency starting to move through repeated-query caching and snippet-first enrichment, and the live backend now hardened around passive standby plus duplicate-runtime refusal
- Last completed phase: `Phase 2 - Contract Versioning`
- Last completed slice: `Phase 3A - Deterministic Action Gaps`
- Next milestone: continue the bounded `Phase 3B` retrieval and knowledge-quality work with broader latency reduction and live provider benchmarking on top of the new indexed weather/fact/GitHub retrieval base

## Phase Status

| Phase | Name | Status | Progress | Notes |
| --- | --- | --- | --- | --- |
| 1 | Hardening | Complete | 100% | Deterministic routing, truthful verification, runtime boundaries, phrase regressions, and the host smoke harness are in place for the current advertised surface |
| 2 | Contract Versioning | Complete | 100% | `/api/v1` is the only supported public API namespace, public payloads are typed, stable capability IDs are emitted from code, and v1 release notes exist |
| 3 | Feature Completion | In Progress | 79% | Provider abstraction is live, summarization has layered extraction fallbacks, indexed page retrieval now reuses KB-backed page snapshots in page summary and fetch/search reads, dedicated weather and quick-fact retrieval now use direct public providers before generic search fallback, GitHub status now resolves tracked project repos and direct `owner/repo` phrases through public API reads before MCP fallback, current-news lookup has an RSS fallback plus repeated-query caching and snippet-first enrichment, calendar reads cover next-event and week-style phrases, browser control covers back/refresh/new-window routing with host smoke on local temp pages, filesystem CRUD now covers common local create/open/read/write/find/list/move/copy/rename/delete/zip flows with broader host smoke, system-control basics now cover common deterministic volume, brightness, lock-screen, dark-mode, DND, screenshot, and battery or wifi phrases, and the remaining work is organized as Phase `3A` to `3D` slices |
| 4 | Performance Profiling | Blocked by earlier phases | 0% | No profiling before reliability and contract stability |

## Phase 1 Progress

### Goal

Fix critical or high issues, stabilize runtime boundaries, and make current features trustworthy.

### Workstream Status

| Workstream | Status | Progress | Notes |
| --- | --- | --- | --- |
| Understanding and lane selection | Complete | 100% | Routing order is pinned in code and tests as `pending -> instant -> skills -> classifier` with added natural calendar and task phrase regressions |
| Session context and pending state | Complete | 100% | Pending follow-ups and multi-turn email drafting are covered by existing session-context and pipeline regressions |
| Typed tools and execution boundaries | Complete | 100% | The current advertised surface runs through the single tool registry and executor dispatch path with validation and confirmation rules |
| Verification layer | Complete | 100% | Filesystem, browser, terminal, project-open, calendar add, Gmail compose, WhatsApp, reminders, and truthful degraded-state narration are wired |
| Runtime boundary cleanup | Complete | 100% | The remaining Phase 1 transport leak in `trigger.py` is removed and the layering regression now covers it |
| Regression and smoke coverage | Complete | 100% | Router, executor, telemetry, memory, instant-lane, and host-smoke coverage now pin the hardened surface |

### What Is Already In Place

- `gemma4:e4b` is the local classifier and hot-path conversation model
- `brain/session_context.py` is wired for pending state and turn memory
- `pipeline/router.py` already has a lightweight reply lane for `question` and `unknown`
- `brain/tools_registry.py` exists as the single tool registry
- `memory/bus.py` is the intended hot-path memory writer
- dashboard command and mic paths now proxy to the live backend instead of running local split-brain execution
- startup briefing is trigger-gated, fresh-session reset paths exist, plain `butler.py` launch now stays in passive standby until clap, wake phrase, or explicit HUD/API activation, and the localhost dashboard defaults to `7532` without native HUD auto-open
- executor results now carry verification metadata and truthful degraded-state messaging for major side-effect families
- touched core modules no longer import dashboard broadcast directly; runtime telemetry owns that bridge
- toolkit wrappers now prefer verification-aware result text over optimistic raw strings

### Residual Operator Prerequisites

- Calendar read is now truthful, but live reads still require Calendar automation access on the host machine
- Mail delivery smoke requires `--mail-to`
- WhatsApp delivery smoke requires `--whatsapp-contact` plus `--whatsapp-message`

### Phase 1 Priority Queue

1. Completed on 2026-04-11: settled one routing order and codified it in docs plus tests:
   pending -> instant -> skills -> classifier -> lane -> executor -> memory bus -> speech
2. Completed on 2026-04-11: added explicit verification hooks for the highest-value side effects:
   filesystem, browser, terminal, project-open, calendar add, Gmail compose, WhatsApp, reminders
3. Completed on 2026-04-12: pinned the remaining high-risk phrase regressions for casual replies plus natural calendar and task phrasing
4. Completed on 2026-04-12: added `scripts/system_check.py --phase1-host --phase1-host-only` for the safe host smoke set and explicit operator-gated skips
5. Completed on 2026-04-12: started Phase 2 with `/api/v1` aliases, versioned HUD envelopes, typed DTOs, and initial contract notes

## Phase 2 Progress

### Goal

Freeze stable interfaces so Burry can evolve without breaking the HUD, tools, or clients every session.

### Workstream Status

| Workstream | Status | Progress | Notes |
| --- | --- | --- | --- |
| HTTP versioning | Complete | 100% | dashboard and A2A now expose only `/api/v1/...` on the public contract surface |
| WS envelope versioning | Complete | 100% | HUD events include `event_version`, `type`, `ts`, and `data`; legacy `payload` remains mirrored only for compatibility |
| Typed DTOs | Complete | 100% | `CommandRequest`, `CommandResult`, `ToolInvocation`, `ToolResult`, `PendingState`, `ClassifierResult`, `CapabilityDescriptor`, `HudEventEnvelope`, `ApiResponse`, and `ApiError` are live |
| Capability ID freeze | Complete | 100% | stable capability IDs now emit from the live registry and are documented in `.CODEX/Capability_Map.md` |
| Release notes | Complete | 100% | `docs/phases/CONTRACT_RELEASE_NOTES.md` records the v1 contract shape, migration notes, and test evidence |

### What Moved

- dashboard and A2A write paths now use `/api/v1/run`, `/api/v1/listen_once`, and `/api/v1/interrupt`
- dashboard public read paths now use typed `/api/v1/...` envelopes and the frontend has been moved to those routes
- HUD WS transport now emits a stable envelope with `event_version`, `type`, `ts`, and `data`
- typed DTOs for commands, tool calls, tool results, pending state, classifier output, capability descriptors, HUD events, API envelopes, and API errors now live under `capabilities/contracts.py`
- stable capability IDs now emit from `capabilities/registry.py` and the public capability catalog is available at `/api/v1/capabilities`
- targeted regressions now pin the Phase 2 transport slice in dashboard, A2A, telemetry, and contract tests

### What Is Still Pending

- nothing for Phase 2 on the current advertised surface

## Phase 3 Slice Status

| Slice | Status | Notes |
| --- | --- | --- |
| 3A — Deterministic action gaps | Complete | deterministic browser/filesystem/system-control routing, delete/zip/reminder/calendar-write hardening, truthful verification, and `--phase3a-host` evidence are now in place; live calendar writes still skip truthfully on hosts without Calendar automation access |
| 3B — Retrieval and knowledge quality | In Progress | summarization hardening and news fallback landed, current-news timeout filler is rejected before speech, indexed page retrieval now reuses KB-backed page snapshots in page summary and fetch/search reads, weather plus quick-fact lookup now use dedicated public sources before generic search fallback, GitHub status now resolves tracked project repos before MCP fallback, and repeated-query caching plus snippet-first enrichment now reduce avoidable search/news latency; broader retrieval latency and live provider benchmarking still remain |
| 3C — Messaging and project tooling | Queued | Gmail compose and basic terminal/project-open flows exist, but attachments, richer WhatsApp, run-tests, editor openers, git confirmations, and VPS completion work remain |
| 3D — HUD and proactive loops | Queued | pending and mood events already publish, but richer HUD rendering, logs/timing, and smarter heartbeat behavior remain |

## Phase 3 Breakdown

### Entry Conditions

- Phase 2 contracts are frozen
- public tool and event payloads are stable

### Execution Order

1. `3A - Deterministic Action Gaps`
   browser host-smoke, filesystem CRUD correctness, system-control basics, calendar write/reminder verification
2. `3B - Retrieval and Knowledge Quality`
   weather, facts, news latency, GitHub status, page/article/video summarization, indexed retrieval
3. `3C - Messaging and Project Tooling`
   Gmail attachments, WhatsApp refinement, run-tests, editor openers, git confirmations, VPS checks
4. `3D - HUD and Proactive Loops`
   pending UI, mood UI, logs/timing, smarter heartbeat suggestions

## Phase 4 Preview

### Entry Conditions

- Phases 1 through 3 are stable enough that measurements are trustworthy

### Output

- measured hotspot report
- evidence-based optimization plan
- explicit Rust decision only if profiling justifies it

## Active Blockers

- none for Phase 1 on the current advertised surface

## Next Actions

1. Continue `Phase 3B` retrieval and knowledge-quality work on the frozen v1 contracts
2. Keep broader retrieval-latency work and the live provider benchmark path at the front of the `3B` queue now that indexed weather, quick-fact, and GitHub retrieval have landed
3. Keep the v1 contract notes updated only if a future versioned migration becomes necessary
4. Do not reopen the closed `3A` or Phase 2 surfaces casually while adding breadth

## Update Template

Append a new status block after each working session:

```md
## Progress Update - YYYY-MM-DD

- Phase:
- Status:
- What moved:
- What is still blocked:
- Tests run:
- Manual checks:
- Next action:
```

## Progress Update - 2026-04-11

- Phase: `Phase 1 - Hardening`
- Status: tracker created and baseline recorded
- What moved:
  created this live progress file
  set the current phase to Hardening
  captured current workstream percentages and blockers
  linked progress tracking to the new `PHASE.md`
- What is still blocked:
  Phase 1 still needs concrete implementation-by-module breakdown
  verifier coverage remains thin
  several capability-map entries are still behind actual code state or host verification
- Tests run: none, docs-only change
- Manual checks: none
- Next action: turn Phase 1 into a concrete execution checklist by module and capability ID

## Progress Update - 2026-04-11

- Phase: `Phase 1 - Hardening`
- Status: routing order normalized and pinned
- What moved:
  implemented one explicit early-routing source of truth in `pipeline/router.py`
  split `intents/router.py` so instant matching can run before skills without double-running the classifier
  added regressions for `pending -> instant -> skills -> classifier`
  updated `.CODEX/Codex.md` and `docs/phases/PHASE.md` to match the tested order
- What is still blocked:
  verifier coverage is still thin for filesystem, browser, terminal, calendar, Gmail, and WhatsApp
  skills still need typed execution and verification ownership cleanup in later Phase 1 work
  host-machine smoke validation is still incomplete
- Tests run: `mac-butler/venv/bin/pytest mac-butler/tests/test_butler_pipeline.py mac-butler/tests/test_intent_router.py mac-butler/tests/test_instant_lane.py`
- Manual checks: none
- Next action: add verifier hooks for the highest-value side-effecting actions

## Progress Update - 2026-04-11

- Phase: `Phase 1 - Hardening`
- Status: verification layer and runtime boundary cleanup moved forward
- What moved:
  added executor-side verification metadata for filesystem, browser, terminal, project-open, calendar add, Gmail compose, WhatsApp, and reminder actions
  made direct-action narration prefer verification detail over optimistic post-hoc summaries
  made toolkit wrappers surface verification-aware result text instead of raw optimistic strings
  routed touched core HUD event publishing through `runtime.telemetry.publish_ui_event`
  aligned `README.md` and `.CODEX/Codex.md` with the current installed model set and Phase 1 runtime truth
  fixed `.CODEX/Codex.md` to point at `.CODEX/...` files instead of stale `.claude/...` paths
- What is still blocked:
  host-machine smoke validation is still incomplete for calendar read, Mail delivery, WhatsApp delivery, browser, terminal, and filesystem
  exact user-phrase regressions from the capability issue backlog are still incomplete
  capability-map reconciliation still needs a dedicated pass
- Tests run:
  `mac-butler/venv/bin/pytest mac-butler/tests/test_executor.py mac-butler/tests/test_butler_pipeline.py mac-butler/tests/test_memory_writeback.py mac-butler/tests/test_runtime_telemetry.py`
  `mac-butler/venv/bin/pytest mac-butler/tests/test_intent_router.py mac-butler/tests/test_instant_lane.py mac-butler/tests/test_architecture_phase2.py mac-butler/tests/test_session_context.py`
- Manual checks: none
- Next action: pin the remaining phrase failures and add real-machine smoke checks for the still-degraded action families

## Progress Update - 2026-04-12

- Phase: `Phase 1 - Hardening`
- Status: completed for the current advertised surface
- What moved:
  removed the last direct dashboard transport import from `trigger.py`
  added deterministic natural-language regressions for calendar read, calendar add, task add, and casual fast-path replies
  fixed the casual-response ordering bug so `thank you` no longer falls into semantic planning
  built `scripts/system_check.py --phase1-host --phase1-host-only` and exercised the safe host smoke set
  made calendar read fail truthfully with an explicit host-permission message instead of surfacing raw automation errors
  aligned `.CODEX/Codex.md`, `PHASE.md`, `PHASE_PROGRESS.md`, and `README.md` with the tested runtime state
- What is still blocked:
  real Mail delivery smoke still needs `--mail-to`
  real WhatsApp delivery smoke still needs `--whatsapp-contact` and `--whatsapp-message`
  live calendar reads still depend on Calendar automation access on the host
- Tests run:
  `venv/bin/pytest tests/test_trigger.py tests/test_runtime_telemetry.py tests/test_system_check.py tests/test_intent_router.py`
  `venv/bin/pytest tests/test_instant_lane.py tests/test_butler_pipeline.py tests/test_executor.py tests/test_memory_writeback.py tests/test_session_context.py tests/test_architecture_phase2.py tests/test_daemons.py`
- Manual checks:
  `venv/bin/python scripts/system_check.py --json --phase1-host --phase1-host-only`
- Next action: begin Phase 2 contract versioning

## Progress Update - 2026-04-12

- Phase: `Phase 2 - Contract Versioning`
- Status: first contract slice landed
- What moved:
  added typed DTOs in `capabilities/contracts.py` for commands, tool calls, tool results, pending state, classifier output, capability descriptors, and HUD events
  moved dashboard and A2A write paths onto `/api/v1/...` and added `/api/v1` aliases for the dashboard read paths
  switched the frontend to `/api/v1` routes
  wrapped HUD WS traffic in a stable envelope with `event_version`, `type`, `ts`, and `data`, while mirroring legacy `payload` during migration
  added the initial contract notes file at `docs/phases/CONTRACT_RELEASE_NOTES.md`
- What is still blocked:
  stable capability IDs are not yet emitted from the live registry metadata
  legacy `/api/...` aliases still exist and need to be retired before Phase 2 can close
  v1 error and metadata payloads still need one final frozen public pass
- Tests run:
  `venv/bin/pytest tests/test_dashboard.py tests/test_architecture_phase2.py tests/test_a2a_server.py tests/test_runtime_telemetry.py`
- Manual checks:
  `python3 -m py_compile capabilities/contracts.py projects/dashboard.py channels/a2a_server.py tests/test_dashboard.py tests/test_architecture_phase2.py tests/test_a2a_server.py`
- Next action: wire stable capability IDs through the registry and publish the next contract-note update once those IDs are exposed

## Progress Update - 2026-04-12

- Phase: `Phase 2 - Contract Versioning`
- Status: completed
- What moved:
  removed the legacy dashboard `/api/...` aliases and made `/api/v1/...` the only supported public API namespace
  wrapped dashboard GET responses in typed `ApiResponse` envelopes and standardized API errors through `ApiError`
  froze the stable public capability IDs in `capabilities/registry.py` and exposed them through `/api/v1/capabilities` and the A2A agent card
  made pending-dialogue and classifier HUD payloads emit through the typed `PendingState` and `ClassifierResult` DTOs
  aligned `.CODEX/Capability_Map.md`, `README.md`, `.CODEX/Codex.md`, `docs/dashboard_api_contracts.md`, and the v1 release notes with the closed contract surface
- What is still blocked:
  nothing for Phase 2 on the current advertised surface
- Tests run:
  `venv/bin/pytest tests/test_dashboard.py tests/test_a2a_server.py tests/test_capabilities_planner.py tests/test_architecture_phase2.py tests/test_runtime_telemetry.py tests/test_session_context.py`
  `venv/bin/pytest tests/test_executor.py tests/test_butler_pipeline.py tests/test_intent_router.py tests/test_instant_lane.py`
- Manual checks:
  `python3 -m py_compile capabilities/contracts.py capabilities/registry.py capabilities/__init__.py brain/session_context.py intents/router.py executor/engine.py projects/dashboard.py channels/a2a_server.py tests/test_dashboard.py tests/test_a2a_server.py tests/test_capabilities_planner.py tests/test_architecture_phase2.py tests/test_session_context.py`
- Next action: Phase 2 is closed; do not start Phase 3 work until directed

## Progress Update - 2026-04-12

- Phase: `Phase 2 - Contract Versioning`
- Status: closure cleanup completed
- What moved:
  removed the tracked `projects/dashboard.html` runtime artifact so the HUD now serves freshly generated HTML directly
  refreshed `projects/projects.json` for `mac-butler` so the dashboard project card points at `.CODEX/Codex.md`, `docs/phases/PHASE.md`, and `docs/phases/PHASE_PROGRESS.md` instead of deleted remediation docs
  added regressions that pin the live project registry metadata and direct root-route HTML generation
- What is still blocked:
  nothing for Phase 2 on the current advertised surface
- Tests run:
  `venv/bin/pytest tests/test_dashboard.py tests/test_project_store.py tests/test_a2a_server.py tests/test_architecture_phase2.py`
- Manual checks: none
- Next action: keep Phase 2 closed and do not start Phase 3 until directed

## Progress Update - 2026-04-12

- Phase: `Phase 2 - Contract Versioning`
- Status: session-doc maintenance rules clarified
- What moved:
  expanded `.CODEX/Codex.md` so the mandatory closeout list explicitly includes `.CODEX/SPRINT_LOG.md`, `.CODEX/Learning_loop.md`, and conditional `.CODEX/Capability_Map.md` updates
  recorded the miss in `.CODEX/Learning_loop.md` so future sessions treat those files as required closeout work instead of optional notes
- What is still blocked:
  nothing for Phase 2 on the current advertised surface
- Tests run: none, docs-only correction
- Manual checks:
  reviewed `.CODEX/Codex.md`, `.CODEX/Learning_loop.md`, and `.CODEX/SPRINT_LOG.md` together after the update
- Next action: keep using the expanded closeout checklist on every session

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: provider abstraction slice landed
- What moved:
  made `butler_config.py` the source of truth for provider-tagged role models plus STT/TTS target chains
  finished provider-aware LLM routing in `brain/ollama_client.py` for both Ollama and the OpenAI-compatible NVIDIA API surface
  moved classifier, startup briefing, conversation, smart-reply, tool-summary, browser, planner, research, ambient, and specialist-agent helpers onto config-backed role models instead of hard-coded local strings
  made `voice/tts.py` provider-aware with `nvidia_riva_tts -> kokoro -> edge -> say` and Hindi auto-selection for Devanagari text on the NVIDIA path
  made `voice/stt.py` provider-aware with `nvidia_riva_asr -> mlx -> faster-whisper`
  updated focused regressions to assert provider-aware behavior rather than stale local-only model names
- What is still blocked:
  live NVIDIA speech validation still depends on `NVIDIA_API_KEY` and NVIDIA Riva Python clients being installed on the host
  broader Phase 3 feature breadth remains open beyond this provider slice
- Tests run:
  `venv/bin/pytest tests/test_ollama_client.py tests/test_tts.py tests/test_stt.py tests/test_agents.py tests/test_daemons.py tests/test_butler_pipeline.py tests/test_conversation_mode.py`
- Manual checks: none
- Next action: validate the NVIDIA speech path on-host once credentials and Riva clients are present, then continue the remaining Phase 3 feature work

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: summarization slice hardened
- What moved:
  removed the implicit Jina-only dependency from `summarize_page` by adding direct HTML text extraction fallback in `executor/engine.py`
  removed the implicit `youtube_transcript_api` blocker from `summarize_video` by adding direct YouTube caption-track extraction plus `yt-dlp`, Whisper, Jina, and page-text fallbacks
  made the Obsidian video-summary path narrate the save result instead of silently writing the note
  added deterministic phrase coverage so `summarize this article` and `save notes from this video` route to the correct Phase 3 summary actions
- What is still blocked:
  some video hosts still need captions, `yt-dlp`, local Whisper, or Jina fallback before a usable transcript exists
  broader Phase 3 feature breadth is still open beyond summarization and provider abstraction
- Tests run:
  `venv/bin/pytest tests/test_executor.py tests/test_intent_router.py`
  `venv/bin/python -m py_compile executor/engine.py intents/router.py`
- Manual checks: none
- Next action: continue the next bounded Phase 3 feature slice on top of the frozen contracts, with calendar/news/browser correctness still open

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: news slice hardened
- What moved:
  hardened `agents/runner.py` so current-news lookups now use a real fallback chain instead of dropping from thin search results to a generic model answer
  added direct Google News RSS fallback under the existing SearXNG, DuckDuckGo, and Exa search paths
  kept the returned `news` payload truthful by carrying the fallback source list through the agent result data
  added focused regressions for RSS parsing, RSS-backed news collection, and the end-to-end news fallback path
- What is still blocked:
  current-news quality still depends on network reachability even though it no longer depends on one search backend
  broader Phase 3 feature breadth is still open beyond provider abstraction, summarization, and this news slice
- Tests run:
  `venv/bin/pytest tests/test_agents.py tests/test_pipeline_semantic_routing.py tests/test_butler_pipeline.py`
  `venv/bin/python -m py_compile agents/runner.py tests/test_agents.py`
- Manual checks: none
- Next action: continue the next bounded Phase 3 feature slice on top of the frozen contracts, with calendar and browser correctness still open

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: calendar-read slice expanded
- What moved:
  expanded `intents/router.py` so calendar-read phrases now cover next-event, availability, and this-week reads
  hardened `executor/engine.py` `calendar_read` to support `today`, `tomorrow`, `next`, `this_week`, and `next_week` ranges through one executor path
  switched calendar-read narration onto parsed event payloads so the runtime can speak the next event or summarize a week window cleanly instead of surfacing raw date strings
  preserved the explicit host-permission failure message when Calendar automation is unavailable
- What is still blocked:
  live calendar reads still depend on Calendar automation access on the host
  broader Phase 3 feature breadth is still open beyond provider abstraction, summarization, news, and this calendar-read slice
- Tests run:
  `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`
  `venv/bin/python -m py_compile intents/router.py executor/engine.py tests/test_intent_router.py tests/test_executor.py`
- Manual checks: none
- Next action: continue the next bounded Phase 3 feature slice on top of the frozen contracts, with browser correctness and broader calendar write coverage still open

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: session-entry documentation aligned to the live runtime
- What moved:
  clarified `.CODEX/Codex.md` so it pins `mac-butler/` as the implementation root and lists the full mandatory session-start read order
  rewrote `.CODEX/AGENTS.md`, `.CODEX/Codex_Rules.md`, `.CODEX/ARCHITECTURE.md`, and `.CODEX/CHECKLIST.md` to match the current provider-aware routing, `/api/v1` contract surface, and validation discipline
  aligned `docs/phases/PHASE.md` to the same read-order and root-path guidance
- What is still blocked:
  browser correctness and broader calendar write coverage remain the next open Phase 3 feature slices
- Tests run: none, docs-only alignment
- Manual checks:
  read `.CODEX/Codex.md`, `.CODEX/AGENTS.md`, `.CODEX/Codex_Rules.md`, `.CODEX/ARCHITECTURE.md`, `.CODEX/CHECKLIST.md`, and `docs/phases/PHASE.md` together after the rewrite
- Next action: continue the next bounded Phase 3 runtime slice using the clarified session-entry docs

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: browser control slice hardened
- What moved:
  expanded `intents/router.py` so `go back`, `refresh`, and `open a new browser window` route deterministically through the direct browser path
  hardened `executor/engine.py` so browser window, back, refresh, and go-to actions use the resolved browser family instead of hard-coded Chrome
  wired those browser actions through `pipeline/router.py` instant-lane handling and exposed the executor action types through `capabilities/registry.py`
  fixed `capabilities/registry.py` to lazily import Gmail and YouTube router helpers so typed action builders stay stable under package import order
- What is still blocked:
  live browser host behavior is still best confirmed with host smoke or manual browser checks on the machine
  broader Phase 3 feature breadth is still open beyond provider abstraction, summarization, news, calendar read, and this browser slice
- Tests run:
  `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_capabilities_planner.py`
  `venv/bin/python -m py_compile intents/router.py pipeline/router.py executor/engine.py capabilities/registry.py tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_capabilities_planner.py`
- Manual checks: none
- Next action: continue the next bounded Phase 3 runtime slice on top of the frozen contracts, with broader calendar write coverage and remaining browser host-smoke validation still open

## Progress Update - 2026-04-12

- Phase: `Phase 3 - Feature Completion`
- Status: phase tracker restructured around explicit `3A` to `3D` slices
- What moved:
  rewrote `docs/phases/PHASE.md` so Phase 3 is now an execution plan with explicit slices for deterministic actions, retrieval quality, messaging/tooling, and HUD/proactive loops
  aligned `docs/phases/PHASE_PROGRESS.md` so the current focus, next milestone, and active Phase 3 status all point at `Phase 3A` first
  turned the previous broad Phase 3 backlog into an ordered build sequence that can be executed without mixing unrelated workstreams into one patch set
- What is still blocked:
  runtime feature breadth is unchanged; this is a planning and tracking correction, not a runtime feature slice
  `Phase 3A` still needs browser host-smoke, filesystem CRUD correctness, system-control basics, and calendar write/reminder verification
- Tests run: none, docs-only restructuring
- Manual checks:
  read `docs/phases/PHASE.md`, `docs/phases/PHASE_PROGRESS.md`, and `.CODEX/Capability_Map.md` together after the rewrite
- Next action: start the next code slice under `Phase 3A` instead of treating Phase 3 as one undifferentiated backlog

## Progress Update - 2026-04-12

- Phase: `Phase 3A - Deterministic Action Gaps`
- Status: filesystem CRUD slice expanded
- What moved:
  expanded `intents/router.py` so common local-path phrases now route `open_folder`, `open_file`, `read_file`, `write_file`, `find_file`, `list_files`, `move_file`, `copy_file`, and rename-via-move before the generic app-open path
  hardened `executor/engine.py` with fuzzy path resolution across Desktop/Documents/Downloads/Home aliases and directory-preserving move/copy behavior
  kept filesystem results verification-aware by resolving the effective target path before confirming open/write/move/copy outcomes
  added focused router and executor regressions for folder-open, file-open/read/write/find/list, move/copy, and rename behavior
- What is still blocked:
  delete phrase coverage, zip flow, and location-aware create-file placement are still thinner than the rest of the filesystem surface
  broader `Phase 3A` work remains system-control basics, calendar write/reminder verification, and browser host-smoke
- Tests run:
  `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`
  `venv/bin/python -m py_compile intents/router.py executor/engine.py tests/test_intent_router.py tests/test_executor.py`
- Manual checks:
  read `.CODEX/Capability_Map.md`, `README.md`, `projects/frontend/app.js`, and `projects/frontend/modules/{stream,panels}.js` before doc closeout so HUD notes stayed grounded in the actual frontend sections
- Next action: continue the next bounded `Phase 3A` runtime slice with system-control basics or calendar write/reminder verification, while filesystem delete/zip gaps and browser host-smoke remain open

## Progress Update - 2026-04-13

- Phase: `Phase 3A - Deterministic Action Gaps`
- Status: system-control basics slice expanded
- What moved:
  expanded `intents/router.py` so deterministic system-control phrases now cover mute, set-volume, set-brightness, brightness up or down, dark-mode on or off, DND on or off, lock-screen, show-desktop, sleep, and battery or wifi queries
  extended the instant path for exact `brightness up`, `brightness down`, `dark mode on/off`, and `dnd on/off` phrases
  fixed the `brightness` action boundary so `Intent.to_action()` preserves both `level` and `direction`
  hardened `executor/engine.py` with an explicit absolute-brightness execution path instead of silently treating every brightness action like brightness-up
  added focused router and executor regressions for the new system-control phrases and brightness or toggle execution behavior
- What is still blocked:
  broader host smoke is still thin for the system-control actions on the machine
  broader `Phase 3A` work remains calendar write/reminder verification, browser host-smoke, and the thinner filesystem gaps
- Tests run:
  `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`
  `venv/bin/python -m py_compile intents/router.py executor/engine.py tests/test_intent_router.py tests/test_executor.py`
- Manual checks: none
- Next action: continue the next bounded `Phase 3A` runtime slice with calendar write/reminder verification or browser host-smoke, while filesystem delete/zip/create-file gaps remain open

## Progress Update - 2026-04-13

- Phase: `Phase 3A - Deterministic Action Gaps`
- Status: completed for the current advertised surface
- What moved:
  expanded deterministic routing and executor handling for Downloads-targeted file creation, delete-file, zip-folder, and absolute reminder phrasing
  hardened `executor/engine.py` with zip-folder execution, reminder-list verification, natural-time parsing for calendar/reminder writes, `file://`-safe browser normalization, and truthful Calendar automation fallback
  built `scripts/system_check.py --phase3a-host --phase3a-host-only` for broader filesystem CRUD, self-contained browser navigation on local temp pages, reminder verification, calendar-write permission fallback, and safe system-control checks
  aligned `.CODEX/Codex.md`, `.CODEX/Capability_Map.md`, and `README.md` with the tested `Phase 3A` runtime truth
- What is still blocked:
  live calendar reads and writes still depend on Calendar automation access on the host
  disruptive Phase 3A system-control smoke remains operator-gated behind `--phase3a-allow-disruptive-system`
- Tests run:
  `venv/bin/python -m py_compile intents/router.py executor/engine.py butler.py scripts/system_check.py tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_system_check.py`
  `venv/bin/pytest tests/test_executor.py tests/test_system_check.py`
  `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_system_check.py -q`
- Manual checks:
  `venv/bin/python scripts/system_check.py --json --phase3a-host --phase3a-host-only`
  filesystem PASS
  browser PASS on local temp `file://` pages
  reminder PASS
  calendar add SKIP with explicit Calendar automation-access message on this host
  safe system-control PASS
- Next action: begin `Phase 3B - Retrieval and Knowledge Quality`

## Progress Update - 2026-04-16

- Phase: `Phase 3B - Retrieval and Knowledge Quality`
- Status: indexed page retrieval started on the existing retrieval owners
- What moved:
  `memory/knowledge_base.py` now supports cached web-page snapshots with exact source lookup alongside the existing local-file index
  `agents/runner.py` now reuses cached page snapshots in fetch, search rerank, and news enrichment paths and stores fresh Jina page reads back into the knowledge base
  `executor/engine.py` now reuses indexed page snapshots for `summarize_page` before live fetch and stores fetched page text for repeat reads
  focused regressions now pin indexed page readback plus the cache-hit and cache-fill branches for the touched agent and executor paths
- What is still blocked:
  weather and quick-fact quality still depend on the generic search path instead of dedicated retrieval sources
  GitHub status still needs the token-backed integration path
  broader retrieval latency work remains open beyond the new cached page snapshot reuse
- Tests run:
  `venv/bin/python -m py_compile memory/knowledge_base.py agents/runner.py executor/engine.py tests/test_agents.py tests/test_executor.py tests/test_remaining_items.py`
  `venv/bin/pytest tests/test_agents.py tests/test_executor.py tests/test_remaining_items.py -q`
- Manual checks: none
- Next action: continue `Phase 3B` with weather, fact, GitHub-status, and broader latency improvements on top of the new indexed retrieval base

## Progress Update - 2026-04-16

- Phase: `Phase 3B - Retrieval and Knowledge Quality`
- Status: retrieval coverage tightened beyond the initial happy-path pass
- What moved:
  added branch-specific regressions for weather clarification, tomorrow-forecast phrasing, DuckDuckGo infobox fact extraction, Wikipedia stripped-subject fallback, and the dedicated `lookup_weather -> weather` routing contract
  updated the live session docs so every changed behavior now requires new or tightened regressions instead of only rerunning legacy tests
- What is still blocked:
  GitHub status still needs the token-backed integration path
  broader retrieval latency and thinner news-latency work are still open
- Tests run:
  `venv/bin/python -m py_compile agents/runner.py capabilities/registry.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py`
  `venv/bin/pytest tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py -q`
- Manual checks: none
- Next action: continue `Phase 3B` with GitHub-status and broader retrieval-latency work, using branch-specific regressions by default for each new retrieval path

## Progress Update - 2026-04-17

- Phase: `Phase 3B - Retrieval and Knowledge Quality`
- Status: GitHub-status retrieval landed and adjacent session-memory reliability moved forward
- What moved:
  `agents/runner.py`, `capabilities/registry.py`, `capabilities/planner.py`, and `projects/github_sync.py` now support deterministic GitHub-status lookup for tracked projects and direct `owner/repo` phrases through public GitHub API reads before MCP fallback
  `brain/session_context.py` now persists recent turns and pending follow-ups to disk and restores recent snapshots on startup instead of dropping them on restart
  `daemon/bug_hunter.py` now runs only the documented safe phase-scoped host smoke entrypoints
  `scripts/benchmark_models.py` now benchmarks configured Butler and agent role routing on representative prompts so NVIDIA-first routing can be inspected explicitly
- What is still blocked:
  broader retrieval latency and thinner news-latency work are still open
  GitHub private-repo access and higher API limits still depend on `GITHUB_PERSONAL_ACCESS_TOKEN`
  live provider benchmark evidence still depends on host credentials and reachable providers
- Tests run:
  `venv/bin/python -m py_compile brain/session_context.py agents/runner.py capabilities/registry.py capabilities/planner.py projects/github_sync.py daemon/bug_hunter.py scripts/benchmark_models.py tests/test_session_context.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py tests/test_project_store.py tests/test_daemons.py tests/test_model_benchmark.py`
  `venv/bin/pytest tests/test_session_context.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py tests/test_project_store.py tests/test_daemons.py tests/test_model_benchmark.py -q`
- Manual checks:
  `venv/bin/python scripts/benchmark_models.py --json --dry-run`
- Next action: reduce retrieval latency and run the live provider benchmark path against real hosts without reopening the closed `Phase 3A` surface

## Progress Update - 2026-04-18

- Phase: `Phase 3B - Retrieval and Knowledge Quality`
- Status: retrieval latency moved forward on the existing owners
- What moved:
  `agents/runner.py` now reuses a short-lived in-process cache for repeated search and news queries
  news enrichment now skips the live page fetch when the provider snippet is already rich enough and still fetches plus indexes the page when the snippet is too thin
  semantic top-result fetch now also avoids an unnecessary live page read when the leading snippet already carries enough detail
  focused regressions now pin repeated-query cache reuse, rich-snippet skip behavior, thin-snippet fetch behavior, and the semantic top-result skip path directly
- What is still blocked:
  broader retrieval latency still needs live-provider timing evidence on real hosts
  current-news quality still depends on backend reachability even though avoidable fetches are lower now
- Tests run:
  `venv/bin/python -m py_compile agents/runner.py tests/test_agents.py`
  `venv/bin/pytest tests/test_agents.py -q`
- Manual checks: none
- Next action: run the benchmark harness against live providers and keep trimming the remaining retrieval-latency hotspots without reopening the closed `Phase 3A` surface

## Progress Update - 2026-04-18

- Phase: `Phase 3B - Retrieval and Knowledge Quality`
- Status: runtime-entry hardening landed underneath the active retrieval work
- What moved:
  plain `butler.py` startup now enters passive standby instead of auto-STT
  long-lived Butler startup now takes a live-runtime lock so duplicate backends refuse to start
  passive standby now starts the clap path plus optional wake-word path through `trigger.py`, wake-word shutdown is explicit, and clap wake now ignores startup noise plus active sessions
  new runtime regressions now cover passive standby selection, duplicate-lock refusal, duplicate-trigger ignore, clap false-trigger suppression, and wake-daemon shutdown
  `projects/dashboard.py` now supports env-driven HUD port overrides, `butler.py --clap-only` now leaves spoken wake disabled for live host testing, and clap wake now requires a sharp transient instead of any sustained loud block
- What is still blocked:
  spoken wake still depends on the optional `openwakeword` host setup
  broader retrieval latency still needs live-provider timing evidence on real hosts
- Tests run:
  `mac-butler/venv/bin/python -m py_compile butler.py trigger.py daemon/wake_word.py daemon/clap_detector.py tests/test_butler_runtime.py tests/test_trigger.py tests/test_daemons.py`
  `mac-butler/venv/bin/pytest tests/test_butler_runtime.py tests/test_trigger.py tests/test_daemons.py -q`
- Manual checks:
  verified the duplicate-runtime cause against the live host logs before changing the startup path
- Next action: continue `Phase 3B` retrieval and provider-latency work on top of the hardened passive backend surface

## Progress Update - 2026-04-19

- Phase: `Phase 3B - Retrieval and Knowledge Quality`
- Status: live timeout and operator-surface regression fixed
- What moved:
  stopped the live Butler/dashboard runtime processes and verified no Butler, dashboard, trigger, native shell, A2A server, or runner process remained
  changed `projects/dashboard.py` so localhost `7532/7533` is the default dashboard surface and native pywebview HUD/browser auto-open require explicit opt-in
  changed `agents/runner.py` so current-news model timeout filler like `I'm still thinking, give me a moment.` is rejected and replaced with collected headlines/snippets or a truthful unavailable message
  updated `.CODEX/HUD_RUNBOOK.md`, `.CODEX/Codex.md`, `.CODEX/AGENTS.md`, `.CODEX/Capability_Map.md`, `.CODEX/Learning_loop.md`, `.CODEX/SPRINT_LOG.md`, and `README.md` to match the runtime truth
- Tests run:
  `mac-butler/venv/bin/python -m py_compile mac-butler/agents/runner.py mac-butler/projects/dashboard.py mac-butler/trigger.py mac-butler/tests/test_agents.py mac-butler/tests/test_dashboard.py mac-butler/tests/test_trigger.py`
  `mac-butler/venv/bin/pytest mac-butler/tests/test_agents.py::AgentTests::test_news_agent_rejects_timeout_filler_when_items_exist mac-butler/tests/test_agents.py::AgentTests::test_news_agent_rejects_timeout_filler_when_live_fetch_is_empty mac-butler/tests/test_dashboard.py::DashboardTests::test_dashboard_defaults_to_localhost_7532_without_native_hud mac-butler/tests/test_dashboard.py::DashboardTests::test_show_dashboard_window_is_localhost_only_without_hud_opt_in mac-butler/tests/test_trigger.py::TriggerTests::test_start_dashboard_server_announces_live_hud -q`
- Manual checks:
  `ps -ef | rg "butler\.py|projects/dashboard\.py|trigger\.py|native_shell\.py|daemon/heartbeat\.py|daemon/bug_hunter\.py|channels/a2a_server\.py|agents/runner\.py"` returned no live runtime processes
- Next action: continue Phase `3B` provider latency benchmarking and retrieval quality work without reopening the localhost/native-HUD runtime policy
