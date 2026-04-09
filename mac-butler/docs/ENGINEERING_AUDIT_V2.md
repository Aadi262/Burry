# BURRY OS — Engineering Audit
Date: 2026-04-10
Scanned by: Codex
Purpose: Find every violation of good engineering practice

---

## 1. SOLID PRINCIPLES VIOLATIONS

### Single Responsibility
- butler.py:_run_actions_with_response — prepares actions, queues background agents, traces tools, executes actions, coordinates speech threads, rewrites replies, records memory, and mutates runtime state — it SHOULD only coordinate action execution — split into action preparation, action execution, speech coordination, and post-run recording services
- pipeline/router.py:handle_input — starts watchers, resolves pending dialogue, runs skills, invokes semantic planning, chooses execution lane, queues interrupts, calls brain/tool paths, records memory, and mutates state — it SHOULD only route a turn — split into pre-route guards, deterministic lane dispatch, semantic planner adapter, brain escalation, and response finalizer
- pipeline/orchestrator.py:_tool_chat_response — decides fast-path vs AgentScope, runs fallback tool logic, executes toolkit calls, handles interruptions, streams TTS, and synthesizes final speech — it SHOULD only produce tool-chat outcomes — split into fast-path responder, tool-call executor, fallback planner, and speech synthesizer
- executor/engine.py:Executor — owns app launch, browser control, file CRUD, shell execution, git, VPS, messaging, reminders, system controls, and confirmations — it SHOULD only dispatch to domain executors — split into BrowserExecutor, FileExecutor, SystemExecutor, MessagingExecutor, VcsExecutor, and ProjectExecutor
- intents/router.py:IntentResult.to_action — maps every intent into executor payloads across multiple product domains — it SHOULD only map one intent family through metadata — split into per-intent action builders registered in a dispatch table
- intents/router.py:_legacy_route — parses browser, music, files, projects, reminders, news, system, and conversational fallbacks in one linear matcher — it SHOULD only coordinate ordered matchers — split into domain-specific matcher registries
- brain/ollama_client.py:send_to_ollama — selects models, builds planner and speech prompts, calls planner, calls voice model, applies mood/greeting logic, and serializes final JSON — it SHOULD either plan or speak, not both — split into planner prompt builder, planner client, speech prompt builder, and response assembler
- brain/agentscope_backbone.py:AgentScopeBackbone.run_turn — swaps agent instances, injects prompts, manages streaming queues, tracks tool logs, handles interrupts, and normalizes reply payloads — it SHOULD only run one turn against an already-configured agent — split into agent selection, stream forwarding, and reply translation
- memory/store.py:record_project_execution — resolves affected projects, mutates project state, classifies verification commands, formats detail entries, and writes layered memory — it SHOULD only reduce execution results into project state — split project resolution, state reducer, and persistence writer
- projects/dashboard.py:serve_dashboard — boots the HTTP server, defines nested request handlers, routes API calls, serves assets, dispatches commands, and handles interrupts — it SHOULD only start the server — split into controller functions, asset server, and server bootstrap

### Open/Closed
- intents/router.py — adding a new deterministic intent requires editing `INSTANT_PATTERNS`, `_intent_from_action`, `IntentResult.to_action`, `IntentResult.quick_response`, and often `_legacy_route` — fix with an intent registry plus ordered matcher plugins
- executor/engine.py — adding a new action requires editing `_dispatch` and often `_requires_confirmation` — fix with a dispatch table plus action metadata registry
- pipeline/router.py — changing lane policy requires editing `INSTANT_LANE_INTENTS`, `BACKGROUND_LANE_INTENTS`, `_handle_meta_intent`, and `handle_input` — fix with strategy objects or lane registry
- brain/agentscope_backbone.py — adding intent-specific tools or context windows requires editing `INTENT_TOOLS`, `INTENT_TOOL_ALIASES`, `INTENT_CTX`, and `PARALLEL_TOOL_INTENTS` — fix with declarative intent capability config
- projects/dashboard.py — adding a new HUD endpoint or event requires editing `Handler.do_GET`, `Handler.do_POST`, broadcaster helpers, and frontend consumers — fix with route registry and typed event schema
- projects/frontend/modules/stream.js — each new event type adds another hardcoded `if (parsed?.type === "...")` branch — fix with an event-handler dispatch map
- capabilities/planner.py — adding a new semantic capability requires editing `_plan_from_heuristics`, alias normalization, and prompt instructions in `_plan_with_model` — fix with capability plugin registration

### Dependency Inversion
- pipeline/router.py — high-level routing depends directly on the low-level `butler` module singleton via `_butler()` — the correct abstraction is an injected `ButlerRuntime` interface
- pipeline/orchestrator.py — orchestration imports the low-level `butler` entrypoint to reach helpers and state — the correct abstraction is an injected response/orchestration service
- brain/session_context.py — session state depends directly on `projects.dashboard.broadcast_ws_event` — the correct abstraction is an event publisher interface
- memory/store.py — memory logic depends directly on `projects` APIs for project lookup — the correct abstraction is a `ProjectCatalog` interface
- brain/agentscope_backbone.py — the backbone depends directly on dashboard broadcasting and long-term memory writes inside hooks — the correct abstraction is a hook-safe event sink plus memory writer interface
- executor/engine.py — execution depends directly on `intents.router.APP_MAP` — the correct abstraction is a shared app registry owned outside both router and executor
- memory/bus.py — memory recall depends directly on a hardcoded Ollama embeddings HTTP endpoint — the correct abstraction is an injected `EmbeddingClient`

---

## 2. DESIGN PATTERN VIOLATIONS

### God Object
- executor/engine.py — 2076 — action dispatch, AppleScript, browser control, files, git, reminders, VPS, and confirmation UX — split by execution domain behind a registry
- intents/router.py — 1879 — intent grammar, classifier prompt, action mapping, quick responses, and project/app catalogs — split into matcher modules plus intent metadata
- butler.py — 1701 — CLI entrypoint, orchestration, planning, speech, memory, state, interrupts, and startup briefing — split runtime bootstrap from turn coordinator
- agents/runner.py — 1648 — specialist agent orchestration plus HTTP integrations and summarization — split per specialist/provider module
- brain/ollama_client.py — 1291 — prompt templates, backend resolution, auth, retries, sync calls, async calls, and streaming — split prompt building from transport
- pipeline/router.py — 1158 — pending dialogue, skills, semantic planner, lane dispatch, and brain fallback — split into dedicated routing stages
- projects/dashboard.py — 1156 — HTTP server, WS broadcaster, payload shaping, command dispatch, and browser/native HUD boot — split into server, payload, and transport modules
- projects/project_store.py — 1149 — persistence, parsing, status derivation, GitHub enrichment, and heuristics — split store, parser, and health evaluator
- brain/agentscope_backbone.py — 989 — init, toolkit assembly, hook wiring, streaming, compression, and agent caching — split toolkit factory, hook module, and turn runner
- pipeline/orchestrator.py — 894 — prompt shaping, fallback tools, tool chat loop, streaming, and post-action rewrite — split planner, executor, and speech post-processor
- memory/store.py — 742 — embeddings, session persistence, project memory, summaries, and compression — split embeddings, session store, and project state store

### Magic Numbers and Strings
- projects/dashboard.py:56 — `3333` — create `HUD_HTTP_PORT`
- projects/dashboard.py:57 — `3334` — create `HUD_WS_PORT`
- projects/dashboard.py:323 — `0.15` — create `DASHBOARD_WARMUP_POLL_SECONDS`
- projects/dashboard.py:739 — `0.5` — create `OPERATOR_WATCH_INTERVAL_SECONDS`
- brain/agentscope_backbone.py:67 — `8192` — create `INTENT_CONTEXT_WINDOWS["plan_and_execute"]`
- brain/agentscope_backbone.py:72 — `1024` — create `INTENT_CONTEXT_WINDOWS["greeting"]`
- brain/agentscope_backbone.py:555 — `12000` — create `AGENT_COMPRESSION_TRIGGER_TOKENS`
- brain/ollama_client.py:761 — `220` — create `COMPACT_VPS_CONTEXT_LIMIT`
- brain/ollama_client.py:762 — `90` — create `COMPACT_VPS_PLAN_MAX_TOKENS`
- brain/ollama_client.py:763 — `180` — create `VOICE_SPEECH_MAX_TOKENS`
- intents/router.py:1247 — `260` — create `CLASSIFIER_MAX_TOKENS`
- intents/router.py:1248 — `4096` — create `CLASSIFIER_CONTEXT_WINDOW`
- intents/router.py:1337 — `0.4` — create `CONVERSATION_CONFIDENCE_THRESHOLD`
- pipeline/router.py:823 — `0.4` and `0.7` — create `CLARIFICATION_CONFIDENCE_RANGE`
- memory/bus.py:147 — `"http://localhost:11434/api/embeddings"` — create `OLLAMA_EMBEDDINGS_URL`

### Shotgun Surgery
- add a new user action — all files that must change: `intents/router.py`, `pipeline/router.py`, `executor/engine.py`, `brain/tools_registry.py`, `tests/test_intent_router.py`, `tests/test_executor.py`, `tests/test_butler_pipeline.py` — centralize with an action registry carrying route metadata, executor handler, confirmation policy, and test fixture data
- add a new project-opening editor — all files that must change: `executor/engine.py`, `projects/open_project.py`, `intents/router.py`, `butler.py` — centralize with a shared `EditorLauncher` abstraction
- add a new HUD event or operator feed field — all files that must change: `projects/dashboard.py`, `projects/frontend/modules/stream.js`, `projects/frontend/modules/events.js`, `projects/frontend/modules/panels.js`, and every broadcast call site — centralize with typed event contracts
- add a new project-memory attribute — all files that must change: `memory/store.py`, `memory/layered.py`, `projects/project_store.py`, dashboard consumers, and tests — centralize with a project state schema/dataclass

### Feature Envy
- projects/dashboard.py:_command_status_label — uses router output, butler lane constants, and global state more than dashboard-owned data — it should live in a routing status service
- butler.py:_preferred_editor — inspects memory-store project state to infer editor choice — it should live in project launching/project state logic
- memory/store.py:_projects_for_action — knows executor action semantics more than memory semantics — it should live in an action-to-project mapper module
- pipeline/orchestrator.py:_brain_context_text — reaches into butler project snapshot and context-shaping helpers more than local state — it should live in the context builder layer

### Long Parameter Lists
- brain/agentscope_backbone.py:create_react_agent — 10 — group into a `ReActAgentConfig` dataclass
- butler.py:_run_actions_with_response — 7 — group into an `ActionRunRequest` dataclass
- brain/agentscope_backbone.py:AgentScopeBackbone.run_turn — 7 — group into a `TurnRequest` dataclass
- brain/agentscope_backbone.py:run_agentscope_turn — 7 — group into the same `TurnRequest`
- pipeline/orchestrator.py:_safe_tool_chat_response — 7 — group into a `ToolChatRequest` dataclass
- pipeline/orchestrator.py:_tool_chat_response — 6 — group into a `ToolChatRequest` dataclass
- brain/ollama_client.py:_call_ollama — 6 — group into an `OllamaRequest` dataclass
- brain/ollama_client.py:_call_ollama_inner — 6 — group into an `OllamaRequest` dataclass
- brain/ollama_client.py:_call — 6 — group into an `OllamaRequest` dataclass
- brain/ollama_client.py:chat_with_ollama — 6 — group into a `ChatRequest` dataclass
- pipeline/recorder.py:_record — 6 — group into a `RecordedTurn` dataclass
- memory/store.py:_detail_entry — 5 — group into a `ProjectExecutionDetail` dataclass
- pipeline/router.py:_dispatch_research — 5 — group into a `ResearchDispatch` dataclass

### Deep Nesting
- projects/dashboard.py:serve_dashboard.do_GET:942 — nesting depth 4-6 — extract per-route handler methods and SSE loop helper
- projects/dashboard.py:serve_dashboard.do_POST:1083 — nesting depth 5 — extract command, interrupt, and open-project controllers
- pipeline/router.py:handle_input:979 — nesting depth 4 — extract unknown/question brain fallback flows into named functions
- memory/store.py:record_project_execution:418 — nesting depth 4-5 — extract per-action project-state reducers
- brain/agentscope_backbone.py:AgentScopeBackbone._iter_streamed_sentences:767 — nesting depth 4-6 — extract queue parsing and sentence flush helpers
- trigger.py:_run_continuous_session:376 — nesting depth 5 — extract interrupt and stop-command branches

---

## 3. PERFORMANCE ANTI-PATTERNS

### N+1 Problem
- memory/bus.py:168 — `embed()` is called N times against Ollama for each recalled event — batch embeddings or reuse the shared embedding cache
- agents/runner.py:599 — Hacker News item fetch calls `_fetch_json()` once per story ID — batch with bounded parallel fetch or cache item details

### Synchronous Blocking on Hot Path
- pipeline/router.py:821 — `plan_semantic_task()` can synchronously call an LLM before a reply is chosen — estimated latency cost 300ms to 1.5s per ambiguous turn — move semantic planning to async/background or heuristic-only first pass
- capabilities/planner.py:_plan_with_model — synchronous `_call()` sits directly on the voice request path when heuristics miss — estimated latency cost 300ms to 2s — gate behind async planner worker or cached classifier result
- pipeline/orchestrator.py:_smart_reply — blocking `requests.post()` to `/api/chat` — estimated latency cost up to the 15s timeout — switch to async client and race it against simpler fallbacks
- brain/agentscope_backbone.py:run_agentscope_turn — `future.result(timeout=30)` blocks the caller thread until the whole turn completes — estimated latency cost 500ms to 30s — return a streaming future/callback instead of synchronously waiting
- memory/store.py:_embed_text — semantic search/recall issues synchronous embedding HTTP calls — estimated latency cost 100ms to 800ms per recall — move embeddings to cached async service

### Memory Leaks
- brain/agentscope_backbone.py — `_INTENT_TOOLKIT_CACHE`, `_AGENT_CACHE`, and `_MCP_TOOLS_CACHE` grow without eviction across model/intent/server combinations — add maxsize or explicit invalidation policy
- memory/bus.py — `_PENDING` is unbounded if flush stalls or disk write keeps failing — add a max queue size and backpressure/overflow logging

### Repeated Computation
- projects/dashboard.py:operator_snapshot — re-imports modules and reloads runtime/mac/task/mood state on every poll — cache with `functools.lru_cache` or move to event-driven snapshots
- projects/dashboard.py:_dashboard_projects — reparses raw projects for nearly every endpoint and watcher tick — cache by file mtime with `functools.lru_cache`
- memory/store.py:load_recent_sessions — rescans and sorts JSONL sessions on every call — cache by directory mtime with `functools.lru_cache`
- memory/store.py:get_compressed_context — recompresses older sessions from scratch on each background pass — cache compression output by session file mtime

---

## 4. CODE QUALITY VIOLATIONS

### Dead Code
- butler.py:_intent_can_preempt_busy_work — defined at line 1349 — never called from anywhere
- butler.py:_wait_for_runtime_confirmation — defined at line 1420 — never called from anywhere
- butler.py:_get_structured_context — defined at line 1463 — never called from anywhere
- butler.py:_startup_intelligence_line — defined at line 1507 — never called from anywhere
- brain/ollama_client.py:_fallback_speech — defined at line 727 — never called from anywhere
- brain/agentscope_backbone.py:_tool_names_for_intent — defined at line 570 — never called from anywhere
- projects/dashboard.py:_status_rank — defined at line 85 — never called from anywhere

### Duplicate Logic
- intents/router.py:998 vs executor/engine.py:234 — Gmail compose URL generation is duplicated — extract to a shared `gmail_compose_url()` util
- intents/router.py:1017 vs executor/engine.py:344 — folder base-path parsing is duplicated — extract to a shared folder request parser
- intents/router.py:1025 vs executor/engine.py:351 — folder-name cleanup is duplicated — extract to a shared sanitizer
- projects/open_project.py:15 vs executor/engine.py:40 — editor app/CLI candidate lists are duplicated — extract editor launcher config
- projects/open_project.py:101 vs executor/engine.py:377 — editor fallback/open-project launch ordering is duplicated — extract a shared `ProjectOpener`
- brain/tools_registry.py:244 vs skills/imessage_skill.py:13 — iMessage AppleScript send logic is duplicated — extract a shared safe Messages sender

### Silent Failures
- memory/bus.py:58 — event-log append failures are silently dropped — log the error and expose write-back pressure
- memory/bus.py:102 — semantic recall failures silently fall back to keyword search — record the embedding failure reason
- brain/agentscope_backbone.py:112 — HUD broadcast thread creation silently fails — log a warning with payload type
- brain/agentscope_backbone.py:122 — HUD broadcast delivery failure is swallowed — surface broadcaster health and error metrics
- brain/agentscope_backbone.py:355 — plan update broadcast errors are swallowed — log malformed notebook payloads
- projects/dashboard.py:473 — active plan status load failures are hidden — emit degraded-status diagnostics
- intents/router.py:1095 — classifier result broadcast failures are hidden — log the dashboard/event bus failure separately from routing

### Commented Out Code
- None found with high confidence.

### Inconsistent Naming
- email addressee — names used: `to`, `recipient` — canonical name to standardize on: `recipient`
- VS Code editor identity — names used: `vscode`, `code`, `Visual Studio Code` — canonical name to standardize on: `vscode`
- music play action — names used: `spotify_play`, `play_music`, `search_and_play`, `spotify_search_play` — canonical name to standardize on: `play_music` plus a `platform` field
- pending intent kind — names used: `spotify_song`, `spotify_play`, `file_name`, `create_file`, `pending_email`, `compose_email` — canonical name to standardize on final intent names only

### String Concatenation in Loops
- brain/ollama_client.py:1098 — the pattern is `buffer += token` inside a streaming loop — the fix is a chunk list or `io.StringIO`
- brain/ollama_client.py:1154 — the pattern is `buffer += token` inside a streaming chat loop — the fix is a chunk list or `io.StringIO`
- brain/agentscope_backbone.py:768 — the pattern is `buffered_text += delta` inside queue processing — the fix is a chunk buffer with `''.join(...)`

---

## 5. ARCHITECTURE VIOLATIONS

### Circular Dependencies
- butler.py → pipeline/router.py → butler.py — how to break the cycle: inject a runtime interface instead of importing the entrypoint back into the pipeline
- butler.py → pipeline/orchestrator.py → butler.py — how to break the cycle: move shared helpers into a service module owned below the entrypoint
- projects/dashboard.py → intents/router.py → projects/dashboard.py — how to break the cycle: route classifier events through an event bus instead of dashboard imports
- projects/dashboard.py → butler.py → brain/session_context.py → projects/dashboard.py — how to break the cycle: stop publishing HUD events from core state objects

### Layer Violations
- brain/session_context.py — imports `projects.dashboard.broadcast_ws_event` — why this violates layering: brain state depends on HUD delivery — fix: publish domain events through an injected bus
- memory/store.py — imports project lookup helpers from `projects` — why this violates layering: memory depends on an application/UI-adjacent project layer — fix: inject a project catalog interface
- pipeline/router.py — imports the `butler` entrypoint — why this violates layering: a lower pipeline layer reaches upward into the CLI/runtime shell — fix: pass a runtime facade into the router
- pipeline/orchestrator.py — imports the `butler` entrypoint — why this violates layering: orchestration depends on the top-level module instead of stable services — fix: move shared helpers into a lower service module
- projects/dashboard.py — imports `butler.handle_input` and `intents.router.route` — why this violates layering: the UI layer directly drives core internals — fix: expose command/status services
- brain/agentscope_backbone.py — imports `projects.dashboard` in `_ws_broadcast_inner` — why this violates layering: orchestration depends on the dashboard transport — fix: use an event sink abstraction

### Missing Abstraction
- executor/engine.py and projects/open_project.py — the repetition is editor launch discovery and fallback logic — the abstraction to create is `EditorLauncher` / `ProjectOpener`
- brain/session_context.py, brain/mood_engine.py, runtime/telemetry.py, brain/agentscope_backbone.py, and trigger.py — the repetition is direct `broadcast_ws_event` coupling — the abstraction to create is `EventBus`
- brain/ollama_client.py, memory/store.py, memory/bus.py, capabilities/planner.py, and pipeline/orchestrator.py — the repetition is direct Ollama/HTTP transport logic — the abstraction to create is `LLMClient` plus `EmbeddingClient`
- intents/router.py and executor/engine.py — the repetition is shared action/app/project knowledge encoded twice — the abstraction to create is a central command/action registry

### Configuration Scattered
- HUD ports — where it appears: `projects/dashboard.py:56-57`, `projects/native_shell.py:151`, `trigger.py:45` — should be only in butler_config.py
- Ollama local/tracing URLs — where it appears: `butler_config.py:29`, `brain/agentscope_backbone.py:99,140-141`, `memory/bus.py:147`, `projects/dashboard.py:332`, `memory/knowledge_base.py:68` — should be only in butler_config.py
- default project roots `~/Burry/mac-butler` and `~/Developer` — where it appears: `intents/router.py:67-71`, `executor/engine.py:1264,1928`, `brain/tools_registry.py:131`, `tasks/task_store.py:134`, `butler_config.py:9,159` — should be only in butler_config.py
- model identifiers and context windows — where it appears: `intents/router.py:283`, `pipeline/orchestrator.py:147`, `butler.py:302`, `executor/engine.py:230`, `brain/agentscope_backbone.py:67-78`, `brain/ollama_client.py:918` — should be only in butler_config.py

---

## 6. API AND INTERFACE DESIGN

### Inconsistent Return Types
- pipeline/orchestrator.py:_smart_reply — all return types observed: `None`, plain answer string, sentinel strings `NEEDS_TOOLS` and `NEEDS_CONTEXT` — standardize to `SmartReplyResult`
- brain/agentscope_backbone.py:run_agentscope_turn — all return types observed: dict with unstable `metadata` keys copied from AgentScope internals — standardize to a fixed `BackboneTurnResult`
- projects/dashboard.py:serve_dashboard — all return types observed: `ThreadingHTTPServer` or `None` — standardize to `DashboardServerResult`
- intents/router.py:_classifier_intent — all return types observed: `IntentResult` or `None` — standardize to `IntentResult` with an explicit unavailable/error source

### Missing Input Validation
- memory/bus.py:62 — what bad input causes: non-dict `event` raises on `.get` — add validation
- brain/session_context.py:105 — what bad input causes: arbitrary field names mutate pending state and typos silently persist — add validation
- executor/engine.py:935 — what bad input causes: invalid project names or malformed metadata reach subprocess launch paths — add validation
- skills/email_skill.py:13 — what bad input causes: malformed recipients and unbounded bodies produce malformed Gmail URLs — add validation

### Leaking Implementation Details
- projects/dashboard.py — what is exposed: raw runtime `events`, `tool_stream`, `memory_recall`, and observability paths in public dashboard payloads — how to encapsulate: expose a curated dashboard DTO
- brain/agentscope_backbone.py — what is exposed: raw `reply.metadata` from AgentScope is merged directly into public turn results — how to encapsulate: map only supported fields into a stable response model
- brain/session_context.py — what is exposed: internal pending payload structure and timestamps through `get_pending()` — how to encapsulate: return a stable `PendingDialogueState` DTO

---

## 7. TESTABILITY ISSUES

### Untestable Functions
- pipeline/router.py:handle_input — why untestable: mixes state, skills, LLM calls, memory writes, queueing, and audio in one procedure — extract the pure routing decision logic
- executor/engine.py:run_command — why untestable: hardcoded shell execution, filesystem writes, and subprocess output — extract the pure command validation logic
- projects/dashboard.py:serve_dashboard — why untestable: nested handler captures globals and imports runtime modules directly — extract the pure endpoint/controller logic
- brain/ollama_client.py:_call_ollama_inner — why untestable: combines payload construction, transport, fallback chain, and error mapping — extract the pure request builder
- memory/store.py:record_project_execution — why untestable: mixes project lookup, state mutation, detail formatting, and persistence — extract the pure state reducer

### Missing Dependency Injection
- pipeline/router.py:_butler — the hardcoded dependency is the global `butler` module — inject via parameter or constructor
- pipeline/orchestrator.py:_butler — the hardcoded dependency is the global `butler` module — inject via parameter or constructor
- brain/session_context.py:_broadcast_pending — the hardcoded dependency is the dashboard broadcaster — inject via parameter or constructor
- memory/bus.py:_semantic_recall — the hardcoded dependency is the Ollama embedding HTTP call — inject via parameter or constructor
- executor/engine.py:Executor — the hardcoded dependency is `subprocess`, `input`, `time.sleep`, and filesystem state — inject via parameter or constructor
- brain/ollama_client.py:_post_with_thinking_notice — the hardcoded dependency is `requests.post` — inject via parameter or constructor
- projects/dashboard.py:_dispatch_command — the hardcoded dependency is `butler.handle_input` — inject via parameter or constructor

---

## 8. SECURITY AND SAFETY

### Shell Injection Risk
- executor/engine.py:1271 — the risk is user-provided `cmd` reaching `subprocess.run(..., shell=True)` after only first-token allowlisting — the fix is to parse argv and execute without `shell=True`
- brain/tools_registry.py:246 — the risk is AppleScript injection through unescaped `contact` and `message` — the fix is a shared AppleScript string escaper
- skills/imessage_skill.py:14 — the risk is AppleScript injection through unescaped `contact` and `message` — the fix is to reuse `channels/imessage_channel._osascript_literal()`
- projects/open_project.py:65 — the risk is Terminal `do script` string composition for launcher commands — the fix is to use an enum-backed launcher path and avoid freeform script interpolation

### Hardcoded Credentials
- None found in tracked code files; only empty placeholders and secret-loader accessors were present — move any future secrets to butler_secrets

### Missing Timeout
- skills/email_skill.py:23 — the call is `subprocess.run(["open", url])` — add `timeout=N`
- brain/tools_registry.py:204 — the call is `subprocess.run(["osascript", ...])` — add `timeout=5`
- brain/tools_registry.py:211 — the call is `subprocess.run(["osascript", ...])` — add `timeout=5`
- brain/tools_registry.py:218 — the call is `subprocess.run(["osascript", ...])` — add `timeout=5`
- brain/tools_registry.py:225 — the call is `subprocess.run(["pmset", "displaysleepnow"])` — add `timeout=5`
- brain/tools_registry.py:232 — the call is `subprocess.run(["pbpaste"], capture_output=True, text=True)` — add `timeout=5`
- brain/tools_registry.py:239 — the call is `subprocess.run(["pbcopy"], input=text.encode())` — add `timeout=5`
- brain/tools_registry.py:255 — the call is `subprocess.run(["osascript", "-e", script])` — add `timeout=5`
- scripts/vps.py:72 — the call is SSH status subprocesses inside a loop — add `timeout=N`
- scripts/vps.py:96 — the call is `subprocess.run(_build_ssh_command(args.host))` — add `timeout=N` for non-interactive entrypoints
- scripts/vps.py:98 — the call is `subprocess.run(_build_ssh_command(args.host, args.remote_command))` — add `timeout=N`

---

## SEVERITY SUMMARY

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 4 | Command or script injection paths that can execute unintended actions |
| HIGH     | 18 | Core architectural coupling, blocking hot-path work, or silent data-loss risks |
| MEDIUM   | 33 | Maintainability, extensibility, and testability issues that will compound quickly |
| LOW      | 20 | Minor quality issues, naming drift, and cleanup candidates |

---

## TOP 10 FIXES BY IMPACT (ranked)

1. Remove `shell=True` from `executor/engine.py` and escape all AppleScript message/contact inputs — estimated effort: medium
2. Break the `butler` ↔ `pipeline/router` and `butler` ↔ `pipeline/orchestrator` cycles with injected runtime interfaces — estimated effort: high
3. Split `pipeline/router.py:handle_input` into deterministic routing stages plus a post-response coordinator — estimated effort: high
4. Replace `Executor._dispatch`, `IntentResult.to_action`, and `_legacy_route` with registries instead of hardcoded chains — estimated effort: high
5. Extract a shared `EditorLauncher` / `ProjectOpener` and delete the duplicated open-project/editor logic — estimated effort: medium
6. Replace direct `projects.dashboard.broadcast_ws_event` imports with an event bus abstraction across brain/runtime modules — estimated effort: medium
7. Move semantic-planner LLM calls off the synchronous voice hot path or gate them behind async fallbacks — estimated effort: medium
8. Bound `_AGENT_CACHE`, `_INTENT_TOOLKIT_CACHE`, and `memory/bus._PENDING`, and add health logging for dropped writes — estimated effort: low
9. Centralize ports, model IDs, context windows, and default repo paths in `butler_config.py` — estimated effort: low
10. Split `projects/dashboard.py` into server bootstrap, endpoint controllers, payload assembly, and WS broadcasting modules — estimated effort: high

---

## WHAT IS ALREADY GOOD

- `brain/agentscope_backbone.py` already enforces single `agentscope.init()` and keeps WebSocket broadcasts off the main execution path.
- `brain/session_context.py` bounds recent dialogue history and centralizes pending dialogue state instead of scattering globals.
- `memory/store.py` already caps command history, learned patterns, and the in-process embedding cache.
- `pipeline/router.py` preserves a deterministic fast path, a clarification confidence band, and a distinct background lane instead of routing everything through one slow path.
- `executor/engine.py` already has an allowlist plus confirmation hooks for obviously risky actions.
- `projects/dashboard.py` does path containment checks for `/modules/` and `/vendor/` assets, which is the right direction for local server safety.
- Many subprocess and HTTP call sites already include explicit `timeout=` values; the main problem is inconsistency, not total absence of timeouts.
