# Burry Phase Tracker

Last updated: 2026-04-12
Status: Active
Primary rule: `understand -> decide -> act -> verify -> speak`

This file is the live roadmap for turning Burry from a command bot into a local agent loop.
It is the live phase strategy alongside:

- `.CODEX/Codex.md`
- `docs/phases/PHASE_PROGRESS.md`
- the codebase, tests, and `scripts/system_check.py`

Other planning and backlog docs may lag the current implementation and should not override these live files.

## Read Order

Start with the live session index, then follow the full required-reading stack it defines.
All repo-relative paths in these phase docs assume the implementation root is `mac-butler/`.

Minimum implementation-session order:

1. `.CODEX/Codex.md`
2. `.CODEX/AGENTS.md`
3. `.CODEX/Codex_Rules.md`
4. `.CODEX/Learning_loop.md`
5. `.CODEX/SPRINT_LOG.md`
6. `.CODEX/Capability_Map.md`
7. `docs/phases/PHASE.md`
8. `docs/phases/PHASE_PROGRESS.md`

Use `PHASE.md` for stable strategy and `PHASE_PROGRESS.md` for current status.

## Phase Summary

| Phase | Name | Status | Goal | Exit Gate |
| --- | --- | --- | --- | --- |
| 1 | Hardening | Complete | Fix critical or high failures, stabilize runtime boundaries, and make current features reliable | Current advertised feature set works through deterministic routing, typed tools, truthful verification, regression coverage, and host smoke checks |
| 2 | Contract Versioning | Complete | Freeze stable API, WS, tool, and capability contracts | All public payloads are versioned and backed by typed DTOs plus release notes |
| 3 | Feature Completion | In Progress | Finish the missing feature set on top of stable contracts through bounded `3A` to `3D` slices | Each Phase 3 slice lands on existing owners with truthful verification, phrase regressions, and host evidence where applicable |
| 4 | Performance Profiling | Planned | Measure real hotspots after stability, then optimize | Profiling report exists, optimizations are evidence-based, and any Rust decision is justified by data |

## Repo Constraints

These are existing repo rules, not optional architecture ideas.

- Extend existing owners before creating new files
- Keep one owner per core subsystem:
  `intents/router.py`, `pipeline/router.py`, `pipeline/orchestrator.py`, `brain/ollama_client.py`, `brain/tools_registry.py`, `brain/session_context.py`, `memory/bus.py`, `projects/dashboard.py`
- `memory/bus.py` is the only hot-path write path
- `brain/tools_registry.py` is the single tool registry
- `brain/ollama_client.py` is the single LLM caller
- `pipeline/router.py` is a wrapper and lane selector, not a second router
- `executor/engine.py` should keep the dispatch-table pattern, not grow new if-chains
- Do not let stale capability docs override the code, tests, or live host smoke harness

## Product Rule

Burry should behave like a local talking agent with 3 lanes:

- `Talk`: normal conversation, no tools unless required
- `Do`: one clear action, one typed tool call, one verification pass
- `Figure it out`: multi-step planning or research when the task is ambiguous, current, or multi-stage

ReAct is for hard tasks only. It should not sit on the hot path for every request.

## Current Routing Contract

The repo already expects a strict routing flow. Phase 1 should preserve it while cleaning it up:

1. `trigger.py` resets session context and starts briefing
2. STT produces text
3. pending follow-up is resolved first through `brain/session_context.py`
4. instant patterns run before any skill or classifier work
5. skills run after an instant miss and before the classifier
6. the configured classifier role returns typed intent plus params
7. high-confidence action goes direct to executor
8. medium confidence asks one clarification
9. low confidence falls into conversation mode
10. `memory/bus.py` records asynchronously
11. speech narrates the outcome

Phase 1 source of truth for the hot path is now:
`pending -> instant -> skills -> classifier -> lane -> executor -> memory bus -> speech`

## Hot-Path Constraints

- provider selection must stay config-driven, with local fallbacks preserved when NVIDIA is unavailable
- the hot path still needs a truthful fast fallback when the primary provider is unavailable
- `gemma4:26b` stays VPS-only, not local hot path
- The voice pipeline should stay under the repo timing targets wherever possible
- No LLM in hooks
- No `asyncio.run()` inside AgentScope tools
- No blocking WS broadcast
- No synchronous multi-store writes on the voice hot path

## Core Loop

1. `Understand`
   Turn messy user text into structured JSON:
   `intent`, `params`, `confidence`, `needs_tools`, `needs_context`, `risk`
2. `Decide`
   Pick exactly one lane:
   `chat`, `direct_action`, `planner`, or `research`
3. `Act`
   Call typed tools only. No raw machine-operating strings from the model.
4. `Verify`
   Read the world back and confirm the action actually worked.
5. `Speak`
   Narrate outcome naturally:
   success, pending info needed, or failure reason

## The 5 Brains

### 1. Understanding Brain

- Local structured classifier is the front door
- Regex is only for tiny instant commands:
  `pause`, `mute`, `new tab`, `stop`, `interrupt`
- Output must stay typed and machine-readable

### 2. Decision Brain

- Owns lane selection
- Must decide between:
  `chat`, `direct_action`, `planner`, `research`
- Must not let every request fall into AgentScope or a planner loop

### 3. Action Brain

- Owns typed tool execution
- Example tool surface:
  `open_app`, `create_file`, `calendar_read`, `browser_search`, `summarize_page`, `send_email`
- No fuzzy execution logic inside prompts

### 4. Verification Brain

- Confirms side effects by reading the world back
- Examples:
  created file -> check filesystem
  opened tab -> check browser state
  reminder or event -> check Calendar state
  sent message -> confirm compose/send state

### 5. Narration Brain

- Turns internal state into plain spoken language
- Should explain:
  what Burry did
  what Burry is waiting for
  why something failed

## Target Runtime Shape

The architecture should converge toward this module layout:

- `brain/session_context.py`
  last turns, pending follow-up, current goal, unresolved slots
- `intents/router.py`
  natural language to structured JSON
- `pipeline/router.py`
  `chat` vs `direct_action` vs `planner` vs `research`
- `executor/`
  typed tools and domain executors
- `context/` plus executor state readers
  filesystem, browser, calendar, app state, clipboard, screen reads
- verifier helpers inside an existing owner module or a new domain module only if truly needed
  tool-specific success checks
- `memory/bus.py`
  async event log only, not a fragmented write graveyard
- `runtime/event_bus.py`
  HUD and telemetry fanout with no direct UI imports from core
- `brain/conversation.py` plus `pipeline/speech.py`
  concise natural replies from structured outcomes

If a new file is added, it should exist because it owns a genuinely new domain, not because an existing owner was ignored.

## Never Again Rules

These rules apply in every phase.

- No feature is considered shipped unless it has:
  route -> tool -> verify -> narrate -> tests
- No model is allowed to directly operate the machine with raw strings
- No core module should import dashboard or UI transport code directly
- No user-facing API or WS payload should stay unversioned
- No feature should be advertised in `README.md` unless it is reliable on the host machine
- No background task should acknowledge work without a final completion or failure event
- No bug fix is done until the exact user phrase becomes a regression test
- No destructive file action ships without confirmation rules
- No performance rewrite happens before stability and profiling data exist
- No capability ID is ever reused for a different meaning
- No second router, second tool registry, second LLM caller, or second hot-path memory writer gets created
- No model outside the installed local set should be referenced in architecture or runtime docs

## Phase 1: Hardening

### Mission

Fix critical and high audit issues, stabilize runtime boundaries, and make the current feature surface dependable.

### What This Phase Must Do

- Replace regex-first understanding with a local structured classifier as the normal front door
- Keep regex only for tiny instant commands
- Make lane selection explicit and predictable
- Add typed working memory across turns
- Add verification for all current high-value side effects
- Remove core-to-UI coupling through a real event bus boundary
- Close the critical and high reliability gaps already called out in the audits

### Priority Workstreams

#### 1. Understanding and Lane Selection

- Front-load a local JSON classifier
- Keep `intents/router.py` as the one classifier owner
- Keep `pipeline/router.py` as wrapper plus lane selector only
- Make `question` and messy natural language work without exact command phrasing
- Ensure one-turn chat does not fall into ReAct by default
- Make `planner` and `research` explicit lanes, not accidental fallbacks

#### 2. Session Context

- Track:
  recent turns
  pending fields
  current goal
  unresolved references
- Follow-ups like `with subject hello` must merge into the active draft cleanly

#### 3. Typed Tools and Execution Boundaries

- Every action must enter through a typed tool contract
- Keep `brain/tools_registry.py` as the one tool registry
- Remove fuzzy executor behavior driven by prompt text
- Move shared tool metadata into one stable registry

#### 4. Verification Layer

- Add observers and verifiers for the currently exposed tool families:
  filesystem
  browser
  terminal
  calendar
  gmail
  whatsapp
  reminders
  project open
- Burry should say what actually happened, not what it hoped happened

#### 5. Runtime Boundary Cleanup

- Core logic publishes events to an event bus
- HUD subscribes to events
- Core modules do not import dashboard transports directly
- Async memory bus becomes event logging only, not many write paths on every turn
- `memory/bus.py` remains the only hot-path writer

#### 6. Reliability Backlog To Close In Phase 1

- YouTube vs Spotify routing correctness
- folder and file path correctness
- Terminal duplicate-open behavior
- email parse, pending-slot, and compose correctness
- spoken email normalization correctness
- WhatsApp contact parsing and send semantics
- task and calendar routing from natural phrasing
- news returning one final spoken result
- startup briefing using real signals, not placeholder summaries
- natural chat quality for non-tool questions

### Phase 1 Exit Gate

- Critical and high audit issues are fixed, explicitly deferred, or removed from the advertised surface
- All exposed actions use typed tools with validation
- All exposed side-effecting actions have verification paths or explicit degraded-state messaging
- High-risk natural-language failures are pinned in regression tests
- `scripts/system_check.py --phase1-host --phase1-host-only` passes for the safe host smoke set
- Calendar read, Mail delivery, and WhatsApp delivery are allowed to report explicit operator-gated skips when host permissions or targets are missing
- README claims match what actually works

### Phase 1 Things To Keep In Mind

- Do not add new major features until current ones stop lying
- Hide or mark experimental anything that cannot yet be verified
- Reliability beats breadth in this phase
- Keep the model set stable while hardening; avoid model drift during root-cause work

## Phase 2: Contract Versioning

### Mission

Freeze stable interfaces so Burry can evolve without breaking the HUD, tools, or clients every session.

### What This Phase Must Do

- Move public HTTP routes to `/api/v1/...`
- Add `event_version` to every WS payload
- Define typed DTOs for commands, tool calls, results, and pending state
- Freeze a capability map with stable IDs
- Publish release notes for every contract change

### Contract Surface To Version

- HTTP requests and responses
- WebSocket event envelopes
- typed command DTOs
- typed result DTOs
- tool registry metadata
- capability registry IDs
- error payloads
- pending-dialogue payloads

### Required DTOs

- `CommandRequest`
- `CommandResult`
- `ToolInvocation`
- `ToolResult`
- `PendingState`
- `ClassifierResult`
- `CapabilityDescriptor`
- `HudEventEnvelope`

### WebSocket Envelope Rule

Every HUD event should use one stable envelope:

```json
{
  "event_version": "1.0",
  "type": "tool_result",
  "ts": "2026-04-11T00:00:00Z",
  "session_id": "optional",
  "data": {}
}
```

### Capability ID Scheme

Stable capability IDs should reuse the existing `.CODEX/Capability_Map.md` scheme, not replace it silently.

| Prefix | Current Domain | Example |
| --- | --- | --- |
| `Bxx` | Browser control | `B09 Play on YouTube` |
| `Fxx` | Files and folders | `F01 Create file on Desktop` |
| `Exx` | Email | `E04 Multi-turn compose` |
| `Wxx` | WhatsApp | `W02 Send to contact` |
| `Mxx` | Music and media | `M09 Summarize YouTube video` |
| `SYxx` | System control | `SY17 Check battery` |
| `Txx` | Terminal and code | `T01 Open Terminal` |
| `Cxx` | Calendar and tasks | `C07 Mark task done` |
| `Kxx` | Search and knowledge | `K03 News on topic` |
| `Vxx` | Vision and screen | `V02 Read screen` |
| `Ixx` | Conversation and intelligence | `I01 Session memory` |
| `Hxx` | HUD frontend | `H12 Shows session context/pending` |

If the project wants a dedicated `Nxx` namespace for news later, that must be a versioned migration with release notes and backward-compatibility notes. Do not rename `K03` to `N03` silently.

### Release Note Rule

Every version change must record:

- version number
- added capabilities
- changed payloads
- deprecated fields
- migration notes
- test evidence

### Phase 2 Exit Gate

- `/api/v1` is the only supported public API namespace
- all public WS events include `event_version`
- public payloads use typed DTOs
- capability IDs are stable and documented
- release notes exist for `v1`

### Phase 2 Things To Keep In Mind

- Do not rename fields casually once they are public
- Do not leak internal objects to the HUD
- A good contract is smaller than the internal implementation
- Capability IDs should line up with `.CODEX/Capability_Map.md`
- Any contract migration must update the capability map and release notes together

## Phase 3: Feature Completion

### Mission

Finish the missing feature set only after the runtime and contracts are trustworthy.

### Execution Rule

Phase 3 is no longer one undifferentiated backlog.
It should be executed through 4 bounded slices on the existing owners:

| Slice | Focus | Primary owners | Slice exit gate |
| --- | --- | --- | --- |
| 3A | deterministic action gaps | `intents/router.py`, `pipeline/router.py`, `executor/engine.py`, `capabilities/registry.py` | the targeted action families route deterministically, verify truthfully, and have phrase regressions plus host smoke or manual host evidence where applicable |
| 3B | retrieval and knowledge quality | `agents/runner.py`, `agents/research_agent.py`, `brain/tools_registry.py`, `capabilities/registry.py` | current-information flows use public-data or indexed fallbacks, return one clean final result, and stop degrading into model-only narration when fetchable data exists |
| 3C | messaging and project tooling | `brain/session_context.py`, `intents/router.py`, `executor/engine.py`, `projects/open_project.py` | messaging and project-tool actions are clearly split into draft vs send or open vs execute paths, with truthful verification and confirmation rules |
| 3D | HUD and proactive loops | `runtime/telemetry.py`, `projects/dashboard.py`, `projects/frontend/modules/*`, `daemon/heartbeat.py`, `brain/mood_engine.py` | runtime state is visible in the HUD, timing/log filters exist, and proactive suggestions become explicit tested behaviors rather than vague background ambition |

### Phase 3A — Deterministic Action Gaps

Scope:

- browser host-smoke validation and remaining browser correctness gaps
- filesystem CRUD correctness and Finder-style path handling
- system-control basics
- calendar write and reminder verification

This slice should stay on the existing direct-action owners.
Do not invent new planners or agents for actions that belong in the router and executor.

### Phase 3B — Retrieval and Knowledge Quality

Scope:

- weather and quick-fact quality
- news quality and latency
- GitHub status and project-status lookups
- page, article, and video summarization reliability
- indexed retrieval for pages and documents

This slice should improve the current-information path without reopening Phase 2 contracts.
Prefer public-data fallbacks, cached snapshots, and indexed retrieval over model-only narration.

### Phase 3C — Messaging and Project Tooling

Scope:

- Gmail attachments and richer compose flows
- WhatsApp compose and send refinement
- run-tests actions
- project opener coverage for Claude Code, Codex, Cursor, and related tool flows
- git commit, git push, and VPS checks with proper confirmation and degraded-state handling

This slice should keep side effects explicit:
compose is not send, open is not execute, and destructive project actions still need confirmation rules.

### Phase 3D — HUD and Proactive Loops

Scope:

- pending-session UI depth
- mood-state UI depth
- downloadable and filterable logs
- timing per command
- smarter heartbeat and proactive suggestions

This slice should not add a parallel UI transport.
Build it on the existing versioned HUD envelope and runtime telemetry path.

### Completion Rule For Every Feature

Each feature must have all of the following:

- natural language understanding coverage
- lane selection rule
- typed tool surface
- observer and verifier
- narration behavior
- regression phrases
- host-machine smoke validation
- capability ID and release-note entry if public

### Expected Outputs

- 3A:
  browser, filesystem, system-control, and calendar-write paths behave deterministically on the host and narrate degraded states truthfully
- 3B:
  current-information and summarization paths use layered retrieval, produce one final answer, and can reuse indexed material instead of refetching everything every time
- 3C:
  messaging and project-tool actions are clearly modeled, confirmed, and verified
- 3D:
  the HUD shows pending state, mood, timing, and actionable logs cleanly, and proactive suggestions become a real runtime feature instead of a backlog note

### Phase 3 Exit Gate

- Every completed Phase 3 slice has shipped against the intended owners, not through sidecar workarounds
- Target feature set works end to end on the host machine
- Each completed feature has phrase regressions and smoke evidence
- Incomplete features are hidden or clearly marked experimental

### Phase 3 Things To Keep In Mind

- Finish fewer features properly instead of many features halfway
- Verification quality matters more than demo quality
- If a feature cannot be verified yet, keep the narration honest about that
- Do not mix deterministic action work, retrieval quality work, messaging/tooling work, and HUD/proactive work into one unbounded patch set

## Phase 4: Performance Profiling

### Mission

Measure the real hot path after stability, then optimize only what data proves is expensive.

### Rules For This Phase

- Start only after Phases 1 through 3 are stable enough to trust measurements
- Profile real user flows, not synthetic micro-benchmarks only
- Fix the highest-impact bottlenecks first
- Decide on Rust only after profiling proves Python is the bottleneck

### What To Measure

- classifier latency
- lane-selection latency
- tool dispatch latency
- verification latency
- narration latency
- model response latency
- memory bus write volume
- dashboard event throughput
- session startup cost
- end-to-end time for `Talk`, `Do`, and `Figure it out` lanes

### Outputs

- one profiling report per round
- before or after numbers for each optimization
- hot-path traces for common tasks
- a written decision on whether Rust is actually justified

### Rust Decision Rule

Rust is worth considering only if:

- the hotspot is proven by traces
- the contract is already stable
- the Python design is already clean
- the expected win is meaningful on real workloads

Otherwise, keep the system in Python and simplify first.

### Phase 4 Exit Gate

- hotspot list is backed by measured traces
- optimizations show real improvement
- Rust decision is evidence-based, not aspirational

## Immediate Next Build Order

1. Keep Phase 2 closed and stable; do not casually reopen the public contract surface
2. Execute Phase `3A` first:
   browser host-smoke, filesystem CRUD correctness, system-control basics, calendar write and reminder verification
3. Then execute Phase `3B`:
   weather, facts, news latency, GitHub status, page/article/video summarization, and indexed retrieval
4. Then execute Phase `3C`:
   Gmail attachments, WhatsApp refinement, run-tests, editor openers, git confirmations, and VPS checks
5. Then execute Phase `3D`:
   pending UI, mood UI, logs and timing, smarter heartbeat suggestions
6. Only after the Phase 3 slices are stable should profiling begin

## Session Update Template

Add a new note at the bottom of this file after each working session:

```md
## Session Update - YYYY-MM-DD

- Phase:
- Goal:
- Files changed:
- Tests run:
- Manual host checks:
- Regressions added:
- New risks:
- Next step:
```

After each working session, update `docs/phases/PHASE_PROGRESS.md` first, then append the session note here if the roadmap itself changed.

## Current Guidance

- Build Burry as a local agent loop, not a giant command matcher
- Keep the hot path simple:
  understand once, choose one lane, execute typed tools, verify, narrate
- Use ReAct only when the task is genuinely multi-step or uncertain
- Keep the core clean enough that the HUD is just a subscriber, not part of the brain

## Session Update - 2026-04-11

- Phase: roadmap alignment
- Goal: turn the earlier roadmap into one live tracker aligned with the repo's actual agent-loop rules
- Files changed: `docs/phases/PHASE.md`
- Tests run: none, docs-only change
- Manual host checks: none
- Regressions added: none
- New risks: `Codex.md` still references `.claude/` paths while the current repo folder is `.CODEX/`; this can cause future docs misses if not checked carefully
- Next step: use this file as the live tracker for Phase 1 hardening work and keep it aligned with `.CODEX/Capability_Map.md`
