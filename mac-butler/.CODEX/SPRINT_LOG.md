Sprint Log — what was done, what broke, what was learned
Sprint: AgentScope Integration (Apr 2026)
Commits: 5c97615 → f0c97d5
Done

AgentScope Toolkit replacing 200-line if/elif
MsgHub fanout in agents/runner.py
Streaming TTS via stream_printing_messages
Skills auto-loader (skills/ directory)
Memory compression (get_compressed_context)
QPM rate limiter (brain/rate_limiter.py)
OTel tracing (runtime/tracing.py)
iMessage channel (channels/imessage_channel.py)
async httpx client for daemons
Pydantic structured output (brain/structured_output.py)
MCP tool cache at startup
Persistent event loop (no per-turn asyncio.run)
Intent-scaled num_ctx (greeting=1024, research=8192)
Single agentscope.init (ensure_agentscope_initialized)
All 5 lifecycle hooks registered
Frontend WS handlers for all AgentScope events
Full TOOL_MAP (15+ tools with icons)
New HUD panels (agent-trace, tool-exec, plan-steps)
PlanNotebook → WS plan_update events
OTel tracing URL auto-detect (Phoenix at :4318)
AgentScope RAG with SimpleKnowledge + MilvusLite
Session persistence (save_session_state on SIGTERM)
RL episode wrapper
A2A server with AgentScope native fallback
iMessage AppleScript fallback fix (7539bd7)
_ws_broadcast made non-blocking (f0c97d5)
pre_reply_hook LLM call removed (f0c97d5)
.claude/ docs added and pushed (3ade1de)

Broken and fixed

pre_reply_hook was calling LLM → 70s response time
Fix: hooks must ONLY do WS broadcast, never call LLM
Fix: _ws_broadcast must be non-blocking (background thread)
double agentscope.init() → consolidated to ensure_agentscope_initialized
asyncio.run() in planner/research → thread pool dispatch
iMessage AppleScript crash → osascript -e 'return ""' fallback

Package gaps (Apr 2026)

agentscope.agents → no BrowserAgent/DeepResearchAgent
agentscope.server → no AgentService
agentscope.tuner → no record_feedback
agentscope.rag → no KnowledgeBank (use SimpleKnowledge)
All have fallbacks wired

What is NOT done yet (next sprints)

gemma4:e4b as primary intent classifier (NOT done)
session_context wired into trigger.py (NOT done)
mood_engine wired into prompts (NOT done)
startup briefing (brain/briefing.py) (NOT done)
YouTube vs Spotify platform detection (NOT done)
create_folder path parsing bug (NOT done)
terminal double-open bug (NOT done)
email PyAutoGUI fill (NOT done)
conversation mode (NOT done)
file CRUD by voice (NOT done)
volume/brightness osascript (NOT done)
SearXNG running (OFFLINE — bash scripts/start_searxng.sh)
calendar osascript (NOT done)
GitHub MCP token (NOT SET)

[Add new sprint entries here after each session]

Phase 3B Retrieval Test Tightening — 2026-04-16

Completed
- `tests/test_agents.py` now covers more than the basic happy path for the new retrieval work: missing weather location clarification, tomorrow forecast phrasing, DuckDuckGo infobox fact extraction, and Wikipedia stripped-subject fallback
- `tests/test_pipeline_semantic_routing.py` now pins the dedicated `weather` agent route instead of the retired generic-search backend assumption
- `.CODEX/Codex.md` and `.CODEX/AGENTS.md` now explicitly require new or tightened regressions for every changed behavior instead of treating old test reruns as sufficient

Validation
- `venv/bin/python -m py_compile agents/runner.py capabilities/registry.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py`
- `venv/bin/pytest tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py -q`

Still pending
- GitHub status remains blocked on token-backed integration work
- broader retrieval latency and news-latency work are still open beyond the new direct weather and fact sources

Next
- continue `Phase 3B` with GitHub-status and broader retrieval-latency work, using branch-specific tests by default for each new retrieval path

Phase 3B Weather and Quick-Fact Retrieval — 2026-04-16

Completed
- `agents/runner.py` now has a dedicated weather agent that reads `wttr.in` first, falls back to Open-Meteo, and speaks concise current or tomorrow-focused summaries instead of routing weather through generic search
- `agents/runner.py` now resolves quick facts through DuckDuckGo instant answers and Wikipedia summaries before the generic search path, so simple factual queries stop depending on search result snippets first
- `capabilities/registry.py` now routes `lookup_weather` through the dedicated `weather` agent instead of the generic `search` agent
- retrieval and routing regressions now pin the new direct-provider weather path, the direct-fact branch, and the preserved generic-search fallback behavior

Validation
- `venv/bin/python -m py_compile agents/runner.py capabilities/registry.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py`
- `venv/bin/pytest tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py -q`

Still pending
- GitHub status remains blocked on token-backed integration work
- broader retrieval latency and thinner news-latency work are still open beyond the new direct weather and fact sources

Next
- continue `Phase 3B` with GitHub-status and broader retrieval-latency reduction on top of the new indexed weather/fact retrieval base

Phase 3B Indexed Retrieval Kickoff — 2026-04-16

Completed
- `memory/knowledge_base.py` now supports indexed web-page snapshots with exact source lookup alongside the existing local-file index
- `agents/runner.py` now reuses cached page snapshots in fetch, search rerank, and news enrichment paths, and stores fresh Jina page reads back into the knowledge base
- `executor/engine.py` now reuses indexed page snapshots for `summarize_page` before live fetch and stores fetched page text for repeat reads
- focused regressions were added for indexed page readback plus the cache-hit/cache-fill branches in the agent and executor retrieval paths

Validation
- `venv/bin/python -m py_compile memory/knowledge_base.py agents/runner.py executor/engine.py tests/test_agents.py tests/test_executor.py tests/test_remaining_items.py`
- `venv/bin/pytest tests/test_agents.py tests/test_executor.py tests/test_remaining_items.py -q`

Still pending
- GitHub status remains blocked on token-backed integration work
- broader retrieval latency work is still open beyond the new indexed page snapshot reuse

Next
- continue `Phase 3B` on top of the new indexed retrieval base with GitHub-status and broader latency improvements

Phase 3A Closure Session — 2026-04-13

Completed
intents/router.py now covers deterministic create-file-in-downloads, delete-file, zip-folder, and absolute reminder phrasing
executor/engine.py now has working zip-folder execution, reminder creation through Reminders.app with reminder-list verification, natural-time parsing for calendar/reminder writes, file-url-safe browser normalization, and truthful Calendar automation fallback for host failures
butler.py now contextualizes pathless `zip this folder` actions onto the active workspace
scripts/system_check.py now has `--phase3a-host --phase3a-host-only` covering broader filesystem CRUD, self-contained browser navigation on local temp pages, reminder verification, calendar-write permission fallback, and safe system-control checks; disruptive system controls remain operator-gated
README.md, .CODEX/Codex.md, .CODEX/Capability_Map.md, and docs/phases/PHASE_PROGRESS.md were aligned to the tested Phase 3A runtime truth

Automated validation
venv/bin/python -m py_compile intents/router.py executor/engine.py butler.py scripts/system_check.py tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_system_check.py
venv/bin/pytest tests/test_executor.py tests/test_system_check.py
venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_system_check.py -q

Host validation
venv/bin/python scripts/system_check.py --json --phase3a-host --phase3a-host-only

Host validation result
filesystem PASS
browser PASS using local temp `file://` targets instead of public example domains
reminder PASS with verified Reminders-list lookup
calendar add SKIP with explicit Calendar automation-access message on this host
safe system-control PASS
disruptive system-control SKIP until `--phase3a-allow-disruptive-system` is provided

Status
Phase 3A deterministic action gaps are complete for the current advertised surface

Next
start Phase 3B retrieval and knowledge quality work on top of the frozen v1 contracts

Phase 3B Retrieval + Session Persistence — 2026-04-17

Completed
- `agents/runner.py`, `capabilities/registry.py`, `capabilities/planner.py`, and `projects/github_sync.py` now support deterministic GitHub-status lookup for tracked projects and direct `owner/repo` phrases through public GitHub API reads before MCP fallback
- `brain/session_context.py` now persists recent turns plus pending follow-up state to disk, restores recent snapshots on startup, and keeps the hot path non-blocking with a debounced snapshot write
- `daemon/bug_hunter.py` now runs the documented safe phase-scoped host smoke entrypoints instead of the broad default smoke path
- `projects/projects.json` was refreshed so the `mac-butler` dashboard card reflects active `Phase 3B` work instead of the stale “Phase 3 not started” state
- `scripts/benchmark_models.py` now benchmarks configured Butler and agent role routing on representative prompts so NVIDIA-first selection and fallback timing can be inspected explicitly
- `README.md`, `.CODEX/Codex.md`, `.CODEX/AGENTS.md`, `.CODEX/Capability_Map.md`, `.CODEX/Learning_loop.md`, and `docs/phases/PHASE_PROGRESS.md` were aligned with the tested runtime truth

Automated validation
- `venv/bin/python -m py_compile brain/session_context.py agents/runner.py capabilities/registry.py capabilities/planner.py projects/github_sync.py daemon/bug_hunter.py scripts/benchmark_models.py tests/test_session_context.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py tests/test_project_store.py tests/test_daemons.py tests/test_model_benchmark.py`
- `venv/bin/pytest tests/test_session_context.py tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py tests/test_project_store.py tests/test_daemons.py tests/test_model_benchmark.py -q`

Status
Phase 3B now includes dedicated GitHub-status retrieval on the frozen v1 contracts, while recent session-context memory survives short restarts

Next
reduce retrieval latency, run the live provider benchmark path against real hosts, and keep the stronger branch-specific regression bar on each new slice

Phase 3B Retrieval Latency Reduction — 2026-04-18

Completed
- `agents/runner.py` now reuses a short-lived in-process cache for repeated search and news queries on the existing retrieval owners
- news enrichment now skips the live Jina page fetch when the provider snippet is already rich enough, while still fetching and indexing the page text when the snippet is too thin
- semantic top-result fetch now also avoids an unnecessary live page read when the leading provider snippet already carries enough detail
- added new branch-specific regressions for repeated-query cache reuse, rich-snippet skip behavior, thin-snippet fetch behavior, and the top-result semantic skip path

Validation
- `venv/bin/python -m py_compile agents/runner.py tests/test_agents.py`
- `venv/bin/pytest tests/test_agents.py -q`

Still pending
- broader retrieval latency still needs live-provider timing evidence on real hosts through `scripts/benchmark_models.py`
- current-news quality still depends on backend reachability even though avoidable fetches are lower now

Phase 1 Closure Session — 2026-04-12

Completed
trigger.py no longer imports dashboard transport directly; briefing events now publish through runtime telemetry
pipeline/router.py now handles deterministic casual replies before semantic planning so "thank you" stays sub-200ms
intents/router.py now has deterministic natural-language regressions for:
calendar read
calendar add
task add
executor/engine.py now returns an explicit host-permission message for calendar reads instead of leaking raw osascript/JXA failures
scripts/system_check.py now has `--phase1-host --phase1-host-only` for the safe host smoke set:
filesystem
browser
terminal
calendar read
Gmail compose
WhatsApp open
reminders
real Mail send and real WhatsApp send are now explicit operator-gated smoke steps instead of pretending to be always verifiable
README.md, .CODEX/Codex.md, docs/phases/PHASE.md, and docs/phases/PHASE_PROGRESS.md were aligned to the tested runtime truth

Automated validation
venv/bin/pytest tests/test_trigger.py tests/test_runtime_telemetry.py tests/test_system_check.py tests/test_intent_router.py
venv/bin/pytest tests/test_instant_lane.py tests/test_butler_pipeline.py tests/test_executor.py tests/test_memory_writeback.py tests/test_session_context.py tests/test_architecture_phase2.py tests/test_daemons.py
venv/bin/python scripts/system_check.py --json --phase1-host --phase1-host-only

Host validation result
filesystem PASS
browser PASS
terminal PASS
Gmail compose PASS
WhatsApp open PASS
reminder degraded but truthful PASS
calendar read SKIP with explicit host-permission message if Calendar automation access is missing
Mail delivery SKIP until `--mail-to` is provided
WhatsApp delivery SKIP until `--whatsapp-contact` and `--whatsapp-message` are provided

Status
Phase 1 hardening is complete for the current advertised surface

Next
start Phase 2 contract versioning

Architecture Cleanup Session — 2026-04-09

Commits
1a87c2b cleanup 1 remove dead modules and write architecture diagnosis
cfe5af3 cleanup 2 consolidate tool registry
a6bd32a cleanup 3 simplify router orchestration
48e4b39 cleanup 4 wire session context
2ff139f cleanup 5 wire skills before intent routing
802d488 cleanup 6 wire mood engine into tool prompt
7f5dc01 cleanup 7 remove write-only recorder memory writes

Deleted
context/tasks_context.py
vault/__init__.py
vault/loader.py
brain/tools.py
capabilities/resolver.py removed from the working tree after planner inlining

Wired
brain/session_context.py added and connected in butler.py, trigger.py, pipeline/router.py, pipeline/recorder.py
skills/email_skill.py and skills/calendar_skill.py now checked before intent routing
brain/mood_engine.py now injects mood guidance into the active tool-chat system prompt

Memory cleanup
Stopped writing add_to_working_memory() on every turn
Stopped writing record_episode_with_agentscope_feedback() on every turn
Stopped writing append_to_index() on every turn

Validation
Baseline timing captured before cleanup: butler.py --command 'hi how are you' = 2.482s total
Post-cleanup timing: butler.py --command 'hi' = 1.859s total
Full suite: 437 tests OK
top -l 1: PhysMem 15G used, 64M unused

Still not fixed in this cleanup pass
create_folder path parsing bug
terminal double-open bug
name-to-contact resolution for email recipient aliases

Session Progress Snapshot — 2026-04-09

Status
User halted implementation mid-session. This entry records uncommitted progress only.

Done in this session
executor/engine.py partially expanded:
open_app now checks whether an app is already running and activates it instead of blindly reopening
added executor handlers for folder/file CRUD, browser controls, volume controls, brightness controls, screen lock/sleep/show desktop, dark mode, do not disturb, system_info, summarize_page, summarize_video, screenshot/read_screen, git_action, and open_project fallback launching
create_folder logic now strips location phrases from the spoken name and defaults to ~/Desktop
run_command allowlist was expanded
open_url mappings were updated to include docs.new, sheets.new, meet.new, slides.new, notion, linear, figma, GitHub, Vercel, and Railway
compose_email executor path was added with Gmail compose plus PyAutoGUI subject/body filling when both fields are present
compose_whatsapp executor path was added
intents/router.py partially updated:
compose_email now routes to a dedicated executor action instead of a raw Gmail URL
create_folder and create_file action payloads were adjusted toward the new executor methods
open_project action payload now carries editor selection

Not done yet
session_context multi-turn pending-slot flow is not implemented end to end
brain/briefing.py was not created
trigger.py was not updated to speak briefing on every session before STT
dashboard WebSocket broadcasts for pending_update, mood_update, memory_read, classifier_result, and briefing_spoken were not wired
frontend stream/events feed updates were not completed
projects/open_project.py was not aligned with the requested fallback chain
docs/ARCHITECTURE_CLEANUP.md was not updated
tests were not updated for the new executor/router behavior
no automated smoke tests were run
no manual voice tests were run
no per-change commits were created
no push for the implementation work was performed

Executor + Pending + Briefing Session — 2026-04-10

Completed
executor/engine.py expanded and wired for:
open_app activation checks
create_folder path stripping
file CRUD
browser controls
volume/brightness/system toggles
system_info
compose_email and compose_whatsapp
task/calendar/VPS fallback actions
page/video summary helpers
projects/open_project.py now follows claude -> codex -> cursor -> code fallback
intents/router.py fixed deterministic folder parsing and task/system/page routing
brain/session_context.py now supports generalized pending state with ordered missing fields
pipeline/router.py now resolves pending follow-ups generically, including multi-turn compose_email
brain/briefing.py created and trigger.py now speaks a startup briefing before STT on every session
HUD live feed now broadcasts pending_update, mood_update, memory_read, classifier_result, and briefing_spoken
projects/frontend/modules/events.js now keeps 100 events
focused regression suites updated and passing
full unittest discovery passing: Ran 449 tests in 54.165s

Automated timing
greeting command: 2.232s total
news command: 3.057s total
tool command: 2.631s total

Still pending
real host-level manual GUI/voice validation remains partially unverified from Codex
Desktop folder creation, Terminal window counting, Gmail compose fill, and page-summary checks need live host confirmation if exact manual PASS/FAIL is required
commits and push not created yet in this session

Core Voice Stability Session — 2026-04-11

Completed
pipeline/router.py now hard-gates `question` and `unknown` into a lightweight reply lane first, with AgentScope/tool chat only after explicit tool need or live lookup need
long spoken questions no longer fall into the generic 0.4-0.7 clarifier trap because `question` intent confidence stays high and the router skips clarify for `question`/`unknown`
pipeline/orchestrator.py smart reply prompt now treats live/current facts as `NEEDS_TOOLS` and includes recent dialogue so follow-ups are resolved from recent turns more often
butler.py default no-flag startup now stays alive in interactive STT mode instead of running briefing and exiting
runtime/telemetry.py now supports fresh-launch runtime reset so stale heard/spoken/intent/events do not leak into a new HUD session
memory/long_term.py session restore is now bounded and disabled for live launches; brain/agentscope_backbone.py can reset backbone session memory on fresh start
projects/dashboard.py no longer imports local `butler` for typed command, mic, or interrupt paths; it proxies to the backend on `3335`
channels/a2a_server.py now exposes `/health`, `/run`, `/listen_once`, and `/interrupt`, and accepts HUD/backend proxy traffic
projects/frontend/modules/commands.js now supports hold-to-talk style mic interaction and backend mic requests instead of simple local click wiring
trigger.py now uses the same fresh-session reset path as `butler.py` before clap/trigger sessions
startup briefing now falls back to deterministic project briefing instead of speaking `Something went wrong.`
timed-out lightweight question replies no longer leak `I'm still thinking, give me a moment.` as the final spoken answer

Live verification
HUD healthy on `127.0.0.1:3333`
backend healthy on `127.0.0.1:3335`
HUD `/api/command` now reaches backend `/run`
HUD mic path now reaches backend `/listen_once`
fresh launch resets runtime state and clears stale last-heard/intent/turns before the new session starts

Still pending
live answer quality is still degraded under extreme RAM pressure; the code now falls back more cleanly, but low-memory Ollama timeouts still limit answer quality
clap wake and hold-to-talk were wired end to end in code, but physical-device validation is still needed on the host to confirm exact UX timing
commits and push not created yet in this session

Documentation Alignment Session — 2026-04-11

Completed
read the repo master index and required `.CODEX` session docs after initially missing them
added `docs/phases/PHASE.md` as a live 4-phase tracker covering:
Hardening
Contract Versioning
Feature Completion
Performance Profiling
aligned the tracker to the existing repo rules:
`understand -> decide -> act -> verify -> speak`
single-owner module boundaries
`memory/bus.py` as the only hot-path memory write path
`brain/tools_registry.py` as the only tool registry
`brain/ollama_client.py` as the only LLM caller
existing capability IDs from `.CODEX/Capability_Map.md`
documented the current 3-lane design:
`Talk`
`Do`
`Figure it out`

Still pending
`Codex.md` still points at `.claude/...` paths while the repo currently stores these files under `.CODEX/...`
the phase tracker is aligned now, but the docs path mismatch can still mislead future sessions if it is not normalized

Phase Progress Tracking Session — 2026-04-11

Completed
treated `.CODEX/Codex.md` as the required entrypoint before phase docs
updated `docs/phases/PHASE.md` to include an explicit read order:
`.CODEX/Codex.md`
`.CODEX/AGENTS.md`
`.CODEX/Codex_Rules.md`
`.CODEX/Learning_loop.md`
`.CODEX/SPRINT_LOG.md`
`.CODEX/Capability_Map.md`
`docs/phases/PHASE.md`
`docs/phases/PHASE_PROGRESS.md`
added `docs/phases/PHASE_PROGRESS.md` as the live status tracker for:
current phase
phase percentages
workstream progress
blockers
next actions
seeded the first baseline update for `Phase 1 - Hardening`

Still pending
the Phase 1 tracker still needs a concrete module-by-module execution checklist
capability-map statuses still need reconciliation against the current sprint state

Phase 2 Contract Slice Session — 2026-04-12

Completed
added typed Phase 2 DTOs in `capabilities/contracts.py`:
`CommandRequest`
`CommandResult`
`ToolInvocation`
`ToolResult`
`PendingState`
`ClassifierResult`
`CapabilityDescriptor`
`HudEventEnvelope`
versioned the HUD WebSocket envelope in `projects/dashboard.py` with:
`event_version`
`type`
`ts`
`data`
kept legacy WS `payload` mirrored so the current HUD does not break during migration
moved dashboard and A2A write traffic onto `/api/v1/run`, `/api/v1/listen_once`, and `/api/v1/interrupt`
added `/api/v1` aliases for the main dashboard read endpoints and switched the frontend to the versioned routes
added targeted regressions in:
`tests/test_dashboard.py`
`tests/test_architecture_phase2.py`
`tests/test_a2a_server.py`
published initial v1 contract notes in `docs/phases/CONTRACT_RELEASE_NOTES.md`

Validation
`python3 -m py_compile capabilities/contracts.py projects/dashboard.py channels/a2a_server.py tests/test_dashboard.py tests/test_architecture_phase2.py tests/test_a2a_server.py`
`venv/bin/pytest tests/test_dashboard.py tests/test_architecture_phase2.py tests/test_a2a_server.py tests/test_runtime_telemetry.py`

Still pending
stable capability IDs are not yet emitted from the live registry metadata
legacy `/api/...` aliases remain during migration and must be removed before Phase 2 can close
tool registry metadata and error payloads still need one fully frozen public v1 shape

Phase 2 Contract Closure Session — 2026-04-12

Completed
removed the legacy dashboard `/api/...` aliases and closed the public HTTP surface on `/api/v1/...` only
wrapped dashboard GET endpoints in typed `ApiResponse` envelopes and standardized API failures with `ApiError`
froze stable public capability IDs in `capabilities/registry.py` and exposed them through:
`/api/v1/capabilities`
the A2A agent card
made pending and classifier HUD payloads emit through the typed `PendingState` and `ClassifierResult` DTOs
aligned `.CODEX/Capability_Map.md`, `.CODEX/Codex.md`, `README.md`, `docs/dashboard_api_contracts.md`, and the v1 contract notes with the closed surface

Validation
`venv/bin/pytest tests/test_dashboard.py tests/test_a2a_server.py tests/test_capabilities_planner.py tests/test_architecture_phase2.py tests/test_runtime_telemetry.py tests/test_session_context.py`
`venv/bin/pytest tests/test_executor.py tests/test_butler_pipeline.py tests/test_intent_router.py tests/test_instant_lane.py`
`python3 -m py_compile capabilities/contracts.py capabilities/registry.py capabilities/__init__.py brain/session_context.py intents/router.py executor/engine.py projects/dashboard.py channels/a2a_server.py tests/test_dashboard.py tests/test_a2a_server.py tests/test_capabilities_planner.py tests/test_architecture_phase2.py tests/test_session_context.py`

Still pending
nothing for Phase 2 on the current advertised surface

Phase 2 Contract Cleanup Session — 2026-04-12

Completed
removed the tracked `projects/dashboard.html` runtime artifact so the HUD now serves fresh generated HTML directly
updated `projects/projects.json` for `mac-butler` to point at the live phase docs and current contract state instead of deleted remediation files
added regressions that pin:
the root dashboard route serving generated HTML
the `mac-butler` registry entry using live phase files instead of stale remediation references

Validation
`venv/bin/pytest tests/test_dashboard.py tests/test_project_store.py tests/test_a2a_server.py tests/test_architecture_phase2.py`

Still pending
nothing for Phase 2 on the current advertised surface

Session Docs Discipline Fix — 2026-04-12

Completed
expanded `.CODEX/Codex.md` so the mandatory end-of-session list explicitly includes:
`.CODEX/SPRINT_LOG.md`
`.CODEX/Learning_loop.md`
`.CODEX/Capability_Map.md` when capability truth changes
recorded the docs-maintenance miss in `.CODEX/Learning_loop.md` so this does not repeat

Validation
manual doc check only

Still pending
nothing; this was a documentation process correction

Phase 3 Provider Abstraction Plan — 2026-04-12

Goal
make model, STT, and TTS provider selection config-driven so Burry can switch between local runtimes and NVIDIA-backed runtimes without rewriting routing, executor, or lane logic

Scope
1. keep the existing owner modules:
   `butler_config.py`
   `brain/ollama_client.py`
   `voice/tts.py`
   `voice/stt.py`
2. add provider-aware config for:
   LLM roles
   agent roles
   TTS backends
   STT backends
3. support NVIDIA for:
   reasoning and agent LLM roles through the OpenAI-compatible NVIDIA API surface
   speech through configurable NVIDIA Riva-backed providers with local fallbacks preserved
4. preserve local fallbacks so the machine still works when NVIDIA credentials or speech clients are unavailable

Implementation order
1. define provider-aware targets and endpoint metadata in `butler_config.py`
2. refactor `brain/ollama_client.py` into provider-aware request routing while keeping current call sites intact
3. refactor `voice/tts.py` to use configurable backend targets instead of a hard-coded `edge -> kokoro -> say` chain
4. refactor `voice/stt.py` to use configurable backend targets instead of a hard-coded `mlx -> faster-whisper` chain
5. add regressions for:
   provider target parsing
   NVIDIA/OpenAI-compatible request routing
   TTS backend ordering
   STT backend description and fallback selection

Model direction
- planning/reasoning/tool routing:
  `nvidia::nvidia/nemotron-3-super`
- review/search/news/bug work:
  `nvidia::deepseek-ai/deepseek-r1-distill-qwen-32b`
- coding:
  `nvidia::qwen/qwen2.5-coder-32b-instruct`
- local fallback chain stays in place under Ollama for resilience
- TTS target:
  `nvidia_riva_tts::magpie-tts-multilingual`
- STT target:
  `nvidia_riva_asr::parakeet-1.1b-rnnt-multilingual-asr`

Exit criteria for this session
- config can express provider + model target without logic edits
- LLM routing can hit NVIDIA or local Ollama from the same call path
- speech layers expose provider-aware config and truthful fallback behavior
- focused tests pass

Phase 3 Provider Abstraction Implementation — 2026-04-12

Completed
- finished provider-aware model routing in `brain/ollama_client.py` so the existing call paths can hit either Ollama or the OpenAI-compatible NVIDIA API surface
- refactored `voice/tts.py` to honor config-driven TTS targets with `nvidia_riva_tts -> kokoro -> edge -> say`
- refactored `voice/stt.py` to honor config-driven STT targets with `nvidia_riva_asr -> mlx -> faster-whisper`
- made Hindi-capable TTS auto-select on the NVIDIA multilingual path for Devanagari text
- removed remaining hard-coded local model paths from classifier, conversation, startup briefing, smart reply, tool summary, browser, planner, research, ambient, and project-blurb helpers
- moved specialist agent summarization back onto the single LLM caller so agent flows also inherit provider routing
- updated focused regressions to assert provider-aware model behavior instead of stale local-only names

Validation
- `venv/bin/pytest tests/test_ollama_client.py tests/test_tts.py tests/test_stt.py tests/test_agents.py tests/test_daemons.py tests/test_butler_pipeline.py tests/test_conversation_mode.py`

Still pending
- live host validation for NVIDIA speech still depends on `NVIDIA_API_KEY` plus NVIDIA Riva Python clients being present on the machine
- broader Phase 3 feature-completion work is still open beyond this provider slice

Phase 3 Summarization Hardening — 2026-04-12

Completed
- hardened `executor/engine.py` page summarization so `summarize_page` now falls back from Jina Reader to direct HTML text extraction
- removed the hard dependency on `yt-transcript-api` for YouTube/video summarization by adding direct caption-track extraction from the watch page
- added deeper video fallback order in `executor/engine.py`:
  YouTube caption tracks -> `youtube_transcript_api` -> `yt-dlp` subtitles -> local Whisper -> Jina/page extraction
- made `summarize_video(..., save_to_obsidian=True)` return the save result so the user gets truthful narration when notes are written
- extended deterministic routing so `summarize this article` maps to page summary and `save notes from this video` maps to video summary with Obsidian save enabled
- added focused regressions for page-summary fallback, direct caption-track transcript extraction, Obsidian video-save narration, and the new router phrases

Validation
- `venv/bin/pytest tests/test_executor.py tests/test_intent_router.py`
- `venv/bin/python -m py_compile executor/engine.py intents/router.py`

Still pending
- some non-YouTube video hosts still depend on captions, `yt-dlp`, local Whisper, or Jina fallback before a usable transcript exists
- broader Phase 3 feature-completion work is still open beyond the summarization slice

Phase 3 News Hardening — 2026-04-12

Completed
- hardened `agents/runner.py` so `news` no longer falls straight to a generic model answer when search backends are thin
- added direct Google News RSS fallback under the existing SearXNG -> DuckDuckGo -> Exa search chain for current-topic lookups
- kept structured news metadata truthful by carrying the fallback source list through the returned agent payload
- added focused regressions for Google News RSS parsing, RSS-backed item collection, and the end-to-end `news` fallback path

Validation
- `venv/bin/pytest tests/test_agents.py tests/test_pipeline_semantic_routing.py tests/test_butler_pipeline.py`
- `venv/bin/python -m py_compile agents/runner.py tests/test_agents.py`

Still pending
- current-news quality still depends on network reachability even though it no longer depends on one search backend
- broader Phase 3 feature-completion work is still open beyond provider routing, summarization, and this news slice

Phase 3 Calendar Read Expansion — 2026-04-12

Completed
- expanded `intents/router.py` so calendar-read phrases now cover `what's my next meeting`, availability phrasing like `am i free tomorrow`, and `this week` agenda reads
- hardened `executor/engine.py` `calendar_read` to handle `today`, `tomorrow`, `next`, `this_week`, and `next_week` ranges through one owner path
- switched `calendar_read` onto JSON-backed event parsing so spoken summaries can describe the next event or multiple upcoming events instead of surfacing raw date objects
- preserved the truthful degraded-state message when Calendar automation access is unavailable on the host
- added focused regressions for the new router phrases and the richer calendar summary behavior

Validation
- `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`
- `venv/bin/python -m py_compile intents/router.py executor/engine.py tests/test_intent_router.py tests/test_executor.py`

Still pending
- live calendar reads still depend on Calendar automation access on the host
- broader Phase 3 feature-completion work is still open beyond provider routing, summarization, news, and this calendar-read slice

Session Docs Alignment — 2026-04-12

Completed
- pinned `mac-butler/` as the implementation root in `.CODEX/Codex.md`
- expanded the required reading order so sessions read `.CODEX/AGENTS.md`, `.CODEX/Codex_Rules.md`, `.CODEX/Learning_loop.md`, `.CODEX/SPRINT_LOG.md`, and `.CODEX/Capability_Map.md` before the phase docs
- rewrote `.CODEX/AGENTS.md`, `.CODEX/Codex_Rules.md`, `.CODEX/ARCHITECTURE.md`, and `.CODEX/CHECKLIST.md` to match the current provider-aware Phase 3 runtime, `/api/v1` contract surface, and validation discipline
- aligned `docs/phases/PHASE.md` to the same implementation-root and read-order guidance

Validation
- manual doc readback across the touched `.CODEX` files and `docs/phases/PHASE.md`

Still pending
- runtime feature breadth is unchanged; the next bounded Phase 3 slices remain browser correctness and broader calendar write coverage

Phase 3 Browser Control Hardening — 2026-04-12

Completed
- expanded `intents/router.py` so browser control now routes `go back`, `refresh`, and `open a new browser window` deterministically instead of leaving those phrases to weaker fallback paths
- reclaimed bare `go back` from the Spotify previous-track shortcut so browser navigation uses the expected direct action
- hardened `executor/engine.py` so `browser_window`, `browser_go_back`, `browser_refresh`, and `browser_go_to` use the resolved browser family instead of hard-coded Chrome
- wired the new browser intents into `pipeline/router.py` instant-lane handling and `capabilities/registry.py` raw executor action exposure
- fixed `capabilities/registry.py` to lazily import Gmail and YouTube router helpers so typed browser actions do not disappear under module import order
- added focused regressions for browser routing, browser-family AppleScript generation, direct browser navigation pipeline routing, and capability-builder stability

Validation
- `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_capabilities_planner.py`
- `venv/bin/python -m py_compile intents/router.py pipeline/router.py executor/engine.py capabilities/registry.py tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py tests/test_capabilities_planner.py`

Still pending
- live browser host behavior for these controls is still best verified through the host smoke or manual browser checks on the machine
- broader Phase 3 feature-completion work remains open beyond provider routing, summarization, news, calendar read, and this browser slice

Phase 3 Slice Planning Alignment — 2026-04-12

Completed
- rewrote `docs/phases/PHASE.md` so Phase 3 is now split into explicit `3A` through `3D` execution slices instead of one broad feature bucket
- aligned `docs/phases/PHASE_PROGRESS.md` so the current focus and next milestone point at `Phase 3A` deterministic action work first
- aligned the phase docs with `.CODEX/Capability_Map.md` so the next implementation order now matches the owner-based wiring plan

Validation
- manual readback across `docs/phases/PHASE.md`, `docs/phases/PHASE_PROGRESS.md`, and `.CODEX/Capability_Map.md`

Still pending
- runtime behavior is unchanged; the next real implementation slice is still Phase `3A`
- filesystem CRUD correctness, system-control basics, calendar write/reminder verification, and browser host-smoke are still the next code tasks

Phase 3A Filesystem CRUD Expansion — 2026-04-12

Completed
- expanded `intents/router.py` so common local-path phrases now route `open_folder`, `open_file`, `read_file`, `write_file`, `find_file`, `list_files`, `move_file`, `copy_file`, and rename-via-move before the generic app-open path
- hardened `executor/engine.py` with fuzzy local-path resolution across Desktop/Documents/Downloads/Home-style aliases
- preserved filename semantics when moving or copying into a directory so callers do not need to spell the final filename every time
- kept filesystem results verification-aware by resolving the effective target path before confirming open/write/move/copy outcomes
- added focused regressions for folder-open, file-open/read/write/find/list, move/copy, and rename behavior

Validation
- `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`
- `venv/bin/python -m py_compile intents/router.py executor/engine.py tests/test_intent_router.py tests/test_executor.py`

Still pending
- delete phrase coverage, zip flows, and location-aware create-file placement are still thinner than the rest of the filesystem surface
- broader Phase 3A work remains system-control basics, calendar write/reminder verification, and browser host-smoke

Phase 3A System Control Basics — 2026-04-13

Completed
- expanded `intents/router.py` so deterministic system-control phrases now cover mute, absolute volume, absolute brightness, brightness up or down, dark mode on or off, DND on or off, lock-screen, show-desktop, sleep, and battery or wifi queries
- extended the instant path for exact `brightness up`, `brightness down`, `dark mode on/off`, and `dnd on/off` phrases so they avoid the classifier entirely
- fixed the router-to-executor action boundary for `brightness` so direction and absolute-level payloads survive `Intent.to_action()` instead of silently collapsing into the wrong default behavior
- hardened `executor/engine.py` with an explicit `brightness_set()` path so absolute brightness requests no longer degrade into a blind brightness-up action
- added focused regressions for the new system-control router phrases plus the brightness and toggle executor paths

Validation
- `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`
- `venv/bin/python -m py_compile intents/router.py executor/engine.py tests/test_intent_router.py tests/test_executor.py`

Still pending
- host smoke is still thin for the system-control actions even though the deterministic routing and executor paths are now wired
- broader Phase 3A work remains calendar write/reminder verification, browser host-smoke, and the thinner filesystem gaps
