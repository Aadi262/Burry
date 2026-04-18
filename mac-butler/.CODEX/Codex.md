# BURRY OS — Master Index
# READ THIS FIRST. Every session. Before anything else.
# Then read the files listed under REQUIRED READING.

## REQUIRED READING (every session, in this order)
Project workspace root: `/Users/adityatiwari/Burry`
Implementation root for this repo: `mac-butler/`

All repo-relative paths in this file assume you are working inside `mac-butler/`.

1. `.CODEX/Codex.md`               — session entrypoint, repo root, and doc hierarchy
2. `.CODEX/AGENTS.md`              — routing contract, owner map, and operating rules
3. `.CODEX/Codex_Rules.md`         — engineering constraints and anti-patterns
4. `.CODEX/Learning_loop.md`       — mistakes and hard lessons that must not repeat
5. `.CODEX/SPRINT_LOG.md`          — latest implementation history and validation evidence
6. `.CODEX/Capability_Map.md`      — live capability status and setup caveats
7. `docs/phases/PHASE.md`          — stable phase strategy and exit gates
8. `docs/phases/PHASE_PROGRESS.md` — current status and latest validation results

Read these when the session needs them:
- `.CODEX/ARCHITECTURE.md` for the current module/runtime map
- `.CODEX/CHECKLIST.md` before commit or handoff
- `.CODEX/HUD_RUNBOOK.md` when running or debugging the dashboard/HUD

Code, tests, and the live phase docs override stale backlog notes.
Do not let older planning files or deleted `.claude/*` era references override this file, the phase tracker, or the actual runtime.


## AFTER EVERY SESSION (mandatory)
1. Update `.CODEX/Codex.md` if the current runtime truth changed
2. Update `.CODEX/AGENTS.md` if the routing contract, owner map, or validation-floor rules changed
3. Update `.CODEX/SPRINT_LOG.md` with what moved, what was validated, and what remains
4. Append `.CODEX/Learning_loop.md` with mistakes, hard lessons, and test insights from the session
5. Update `.CODEX/Capability_Map.md` if capability status, IDs, or setup requirements changed
6. Update `docs/phases/PHASE_PROGRESS.md` with what moved and what remains
7. Update `README.md` if user-facing behavior or setup requirements changed
8. Add or tighten regressions for every changed behavior; do not rely only on previously existing happy-path tests
9. Run the relevant tests and host smoke checks before claiming a phase is closed

Docs-only sessions still require a readback pass across the touched `.CODEX` and phase files before handoff.

## FILE MAP — what every file does

### Entry Points
- butler.py          — main voice pipeline, 3500+ lines, God Object being split
- trigger.py         — clap/keyboard trigger, starts session, calls briefing
- state.py           — global Butler state machine (IDLE/LISTENING/THINKING/SPEAKING)

### Brain
- brain/session_context.py    — turn memory, pending dialogue, get_context() singleton
- brain/mood_engine.py        — personality and mood by time/activity
- brain/briefing.py           — startup briefing (GitHub + weather + tasks + calendar)
- brain/conversation.py       — natural conversation mode with personality
- brain/ollama_client.py      — ALL LLM calls go through here
- brain/agentscope_backbone.py — AgentScope ReAct loop, hooks, WS broadcast
- brain/toolkit.py            — AgentScope tool registry
- brain/tools_registry.py     — tool definitions (ONE registry, do not create another)
- brain/rate_limiter.py       — QPM rate limiter for LLM calls
- brain/structured_output.py  — Pydantic structured extraction

### Routing
- intents/router.py           — PRIMARY router: instant patterns + config-driven classifier
- pipeline/router.py          — orchestrator: pending check → skills → intent → lane
- pipeline/orchestrator.py    — AgentScope path and tool chat response
- pipeline/recorder.py        — memory writes (bus only, async)
- pipeline/speech.py          — TTS coordination

### Capabilities
- capabilities/planner.py     — semantic task planner
- capabilities/registry.py    — capability registry and tool specs
- capabilities/contracts.py   — tool contracts, transport DTOs, and HUD envelopes

### Executor
- executor/engine.py          — action dispatcher (50+ actions, dispatch table pattern)
- executor/app_state.py       — app running state checks

### Memory
- memory/bus.py               — ONLY write path on hot path (append-only JSONL)
- memory/store.py             — command history, embeddings, semantic search
- memory/long_term.py         — 3-tier: working/recent/archive
- memory/layered.py           — Layer 1 MEMORY.md, Layer 2 project files, Layer 3 sessions
- memory/knowledge_base.py    — RAG with Qdrant/SimpleKnowledge
- memory/rl_loop.py           — model performance tracking
- memory/plan_notebook.py     — plan tracking
- memory/graph.py             — project dependency graph
- memory/learner.py           — pattern extraction

### Skills
- skills/email_skill.py       — email skill (checked BEFORE intent router)
- skills/calendar_skill.py    — calendar skill (checked BEFORE intent router)
- skills/imessage_skill.py    — iMessage skill

### Context
- context/__init__.py         — build_structured_context() from 10 sources
- context/app_context.py      — frontmost app, open windows
- context/git_context.py      — git log, current branch
- context/mac_activity.py     — Mac activity watcher
- context/vscode_context.py   — VS Code/Cursor state
- context/obsidian_context.py — Obsidian vault
- context/vps_context.py      — VPS status
- context/mcp_context.py      — MCP server status

### Agents
- agents/runner.py            — specialist agents (news, search, vps, code, github)
- agents/browser_agent.py     — browser agent with Playwright fallback
- agents/planner_agent.py     — AgentScope meta-planner
- agents/research_agent.py    — deep research agent
- agents/vision.py            — screenshot + vision model

### Projects
- projects/dashboard.py       — HUD server, `/api/v1` surface, and WebSocket transport
- projects/project_store.py   — project registry CRUD
- projects/github_sync.py     — GitHub API sync
- projects/open_project.py    — editor fallback chain (claude→codex→cursor→code)
- projects/native_shell.py    — native HUD window via pywebview

### Frontend
- projects/frontend/app.js         — entry point
- projects/frontend/modules/stream.js    — WebSocket handler, ALL event types
- projects/frontend/modules/panels.js   — left/right rail, TOOL_MAP
- projects/frontend/modules/events.js   — events feed (last 100)
- projects/frontend/modules/orb.js      — Three.js neural orb
- projects/frontend/modules/graph.js    — project graph canvas
- projects/frontend/modules/commands.js — command dock

### Runtime
- runtime/telemetry.py        — live session state tracking
- runtime/tracing.py          — OTel tracing
- runtime/notify.py           — macOS notifications (NOT AppleScript)
- runtime/log_store.py        — log persistence

### Channels
- channels/imessage_channel.py — iMessage polling and reply
- channels/a2a_server.py       — A2A agent-to-agent server and backend `/api/v1` endpoints

### Daemons
- daemon/heartbeat.py          — proactive suggestions every 5 min
- daemon/bug_hunter.py         — background bug scanning
- daemon/ambient.py            — ambient HUD bullet generation
- daemon/clap_detector.py      — double-clap trigger detection
- daemon/wake_word.py          — wake word detection

### Config
- butler_config.py            — ALL configuration (models, keys, paths)
- butler_secrets/loader.py    — secrets loader (NOT secrets/__init__.py)

### Tests
- tests/test_real_scenarios.py     — real end-to-end scenario tests (PRIMARY)
- tests/test_intent_router.py      — intent routing tests
- tests/test_conversation_mode.py  — conversation mode tests
- tests/test_instant_lane.py       — instant pattern tests
- tests/test_executor.py           — executor action tests

### Documentation
- .CODEX/AGENTS.md            — golden rules and architecture
- .CODEX/ARCHITECTURE.md      — full architecture map
- .CODEX/CHECKLIST.md         — pre-commit checklist
- .CODEX/Codex_Rules.md       — engineering rules
- .CODEX/SPRINT_LOG.md        — sprint history
- .CODEX/Learning_loop.md     — mistakes never repeat
- .CODEX/Capability_Map.md    — capabilities tracked
- .CODEX/HUD_RUNBOOK.md       — how to run and debug
- docs/ARCHITECTURE_CLEANUP.md — cleanup audit results
- docs/ENGINEERING_AUDIT_V2.md — latest audit report

## CURRENT STATE (update this section every sprint)

### Working
- config-driven provider routing for LLM, TTS, and STT
- NVIDIA-backed primary model roles with local Ollama fallbacks preserved
- multilingual speech stack via NVIDIA Riva targets with local fallback chains
- browser control now covers new tab, new window, close tab/window, back, refresh, and URL navigation on the resolved browser family
- current-news lookup with search backends plus Google News RSS fallback, repeated-query caching, and snippet-first enrichment so rich provider results avoid unnecessary live page fetches
- weather lookup now uses dedicated public-provider reads through `wttr.in` with Open-Meteo fallback
- quick-fact lookup now prefers DuckDuckGo instant answers and Wikipedia summaries before generic search fallback
- GitHub status lookup now resolves tracked project repos and direct `owner/repo` phrases through public GitHub API reads before MCP fallback
- calendar read now supports today, tomorrow, next event, and this-week phrasing with truthful permission fallback
- filesystem routing now covers common local create/open/read/write/find/list/move/copy/rename/delete/zip phrases with fuzzy path resolution and verification-aware results
- system-control routing now covers common volume, mute, brightness, screenshot, lock-screen, sleep, show-desktop, dark-mode, do-not-disturb, and battery or wifi phrasing on the existing executor actions
- page summarization now reuses indexed web-page snapshots before falling back to Jina and direct HTML extraction
- video summarization with YouTube caption-track extraction plus `yt-dlp` / Whisper / Jina fallback paths
- save-video-summary flow into Obsidian when the vault is configured
- Natural language understanding (not just trigger words)
- Conversation mode with personality
- Session memory across turns, with recent turns and pending follow-ups now restored from disk across short restarts (`session_context.py`)
- Default `butler.py` startup now stays alive in interactive STT mode
- HUD command + mic paths now proxy to the live backend on `3335`
- Fresh launch resets transient runtime state before the new session starts
- Mood engine connected to prompts
- Routing order pinned: pending → instant → skills → classifier
- Verification-aware outcomes for filesystem, browser, terminal, project-open, calendar add, reminders, Gmail compose, and WhatsApp flows
- `scripts/benchmark_models.py` now benchmarks the configured Butler and agent roles on representative prompts so NVIDIA-vs-local routing can be inspected and timed explicitly
- `scripts/system_check.py --phase1-host --phase1-host-only` now covers filesystem, browser, terminal, Gmail compose, WhatsApp open, reminders, and the operator-gated delivery checks
- `scripts/system_check.py --phase3a-host --phase3a-host-only` now covers broader filesystem CRUD, self-contained browser navigation on local temp pages, reminder verification, calendar-write permission fallback, and safe system-control checks
- Calendar read now fails truthfully with an explicit host-permission message instead of surfacing raw `osascript` errors
- Core HUD event publishing now routes through runtime telemetry helpers instead of direct dashboard imports in the touched core modules
- Dashboard and A2A HTTP surfaces now use `/api/v1/...` as the only supported public API namespace
- HUD WebSocket events now use a versioned envelope with `event_version`, `type`, `ts`, and `data`, while mirroring legacy `payload` for compatibility
- Stable public capability IDs now emit from `capabilities/registry.py` and are exposed through the typed capability catalog
- Startup briefing with deterministic fallback
- 50+ executor actions wired
- Multi-turn email pending dialogue
- Timing: 1.8s greeting

### Not Working Yet
- Screen reading (llama3.2-vision not installed)
- richer GitHub MCP actions still depend on MCP server setup and token availability
- SearXNG (Docker not always running)
- WhatsApp file sending
- Claude Code as coding brain (not wired)
- NVIDIA speech paths still require host setup (`NVIDIA_API_KEY` plus NVIDIA Riva Python clients)
- Live answer quality still degrades badly when local RAM is exhausted, Ollama times out, or NVIDIA credentials are absent
- some video hosts still need captions, `yt-dlp` + Whisper, or Jina fallback before a usable transcript exists
- Live calendar reads and writes require Calendar automation access on the host
- Real Mail delivery and WhatsApp send smoke runs require explicit operator-provided targets

### Needs Your Setup
- bash scripts/start_searxng.sh (Docker must be running)
- GITHUB_PERSONAL_ACCESS_TOKEN in butler_secrets for private-repo access, higher GitHub API limits, and better K10 or I08 coverage
- NVIDIA_API_KEY in butler_secrets or env for NVIDIA-backed LLM routing
- NVIDIA Riva Python clients installed for NVIDIA TTS/STT
- OBSIDIAN_VAULT_PATH in butler_config.py
- ollama pull llama3.2-vision

## ROUTING FLOW (strict order, memorize this)
1.  trigger.py → session_context.reset() + briefing
2.  STT → text
3.  ctx.has_pending()? → resolve pending first
4.  12 instant patterns → zero LLM cost
5.  skills.match_skill() → email/calendar/imessage
6.  config-driven classifier → intent + params JSON
7.  confidence > 0.7 → executor directly
8.  confidence 0.4-0.7 → ask clarifying question
9.  confidence < 0.4 → conversation mode
10. memory/bus.py → async write
11. speak response

## MODELS (current runtime shape)
- classifier / fast voice / conversation:
  `nvidia::nvidia/nvidia-nemotron-nano-9b-v2`
  local fallback `ollama_local::gemma4:e4b`
- planning / startup briefing:
  `nvidia::qwen/qwq-32b`
  local fallback `ollama_vps::gemma4:26b` -> `ollama_local::gemma4:e4b`
- review / search / bug hunter:
  `nvidia::deepseek-ai/deepseek-r1-distill-qwen-32b`
  local fallback `ollama_local::deepseek-r1:14b`
- coding:
  `nvidia::qwen/qwen2.5-coder-32b-instruct`
  local fallback `ollama_vps::gemma4:26b` -> `ollama_local::deepseek-r1:14b`
- TTS:
  `nvidia_riva_tts::magpie-tts-multilingual`
  local fallback `kokoro -> edge -> say`
- STT:
  `nvidia_riva_asr::parakeet-1.1b-rnnt-multilingual-asr`
  local fallback `mlx-community/whisper-medium-mlx -> faster-whisper medium.en`
