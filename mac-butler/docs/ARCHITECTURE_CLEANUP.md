# DUPLICATE SYSTEMS (pick one, delete the other):
- intents/router.py vs pipeline/router.py
  Which one is the real router? Which is a wrapper?
  `intents/router.py` is the real deterministic router. It does the actual pattern matching and intent extraction.
  `pipeline/router.py` is the wrapper, but it currently does much more than wrapping: pending-dialogue handling, semantic override, skill dispatch, casual replies, background routing, meta intents, and unknown fallback behavior.
  Decision: keep `intents/router.py`, delete duplicated routing logic from `pipeline/router.py`

- brain/tools.py vs brain/tools_registry.py
  Which one is actually used? Which is dead?
  `brain/tools_registry.py` is the real tool definition file. It owns the `@tool` registrations and the actual callable tool implementations.
  `brain/tools.py` is only a wrapper that imports `brain.tools_registry`, calls `get_toolkit().get_tools()`, and exposes `TOOLS`.
  Decision: keep `brain/tools_registry.py`, delete `brain/tools.py`

- capabilities/planner.py vs capabilities/registry.py vs capabilities/resolver.py
  Are all 3 needed? What does each one do?
  `capabilities/planner.py` maps freeform text into a typed `CapabilityTask`.
  `capabilities/registry.py` is the canonical capability/tool catalog. It maps semantic tool names to executor actions and metadata.
  `capabilities/resolver.py` is only helper logic for planner-time argument normalization: runtime snapshot lookup, frontmost-app resolution, folder parsing, weather parsing, and YouTube query cleanup.
  Only two layers are justified here: planner + registry. Resolver is not a separate architectural system; it is planner support code.
  Decision: keep `capabilities/planner.py` and `capabilities/registry.py`, delete `capabilities/resolver.py`

# DEAD FILES (built but never imported anywhere):
- `context/tasks_context.py`
  Exists, but nothing imports it. Live task context comes from `tasks.task_store` through `context/__init__.py`.
- `vault/loader.py`
  Exists, but nothing imports it. Live secret loading uses `butler_secrets.loader`.
- `vault/__init__.py`
  Exists, but nothing imports it. It is only supporting the dead `vault` package.

# UNWIRED FILES (imported but functionality not connected):
- skills/email_skill.py — is match_skill() called in butler.py?
  No. `butler.py` does not call `match_skill()`.
  `match_skill()` is only called inside `pipeline/router.py`, and it runs too late in the pipeline: after early intent routing, instant/background lane short-circuits, and busy-state checks.

- skills/calendar_skill.py — same
  Same problem. It is auto-loaded by `skills/__init__.py`, but the main pipeline does not check skills early enough.

- brain/mood_engine.py — is get_mood() used in any prompt?
  Not in the active tool-chat prompt path.
  `brain/ollama_client.py` imports `describe_mood_state()` and `send_to_ollama()` includes mood in its speech prompt, but `pipeline/orchestrator.py` does not inject `get_mood()` / `get_mood_instruction()` into `TOOL_SYSTEM_PROMPT` or `_tool_chat_messages()`.

- brain/query_analyzer.py — is it called anywhere?
  Yes.
  It is called in `butler.py`, `capabilities/planner.py`, and `pipeline/orchestrator.py`.
  This file is wired and should be kept.

- brain/session_context.py — does it exist? is it wired?
  No. The file does not exist.
  It is not wired anywhere.
  Current behavior is split across:
  `pipeline/recorder.py:ConversationContext` for recent turns
  `butler.py:_SESSION_CONVERSATION` for in-process turn memory
  `pipeline/router.py:_PENDING_DIALOGUE` for email/song/file follow-ups

# BROKEN CONNECTIONS (defined but path never reaches):
- session_context pending dialogue — does it resolve email multi-turn?
  No, because `brain/session_context.py` does not exist.
  Email multi-turn currently works only through `pipeline/router.py` global `_PENDING_DIALOGUE`, not through a reusable session-context object.
  The follow-up path is:
  `handle_input()` -> `_resolve_pending_dialogue()` -> `compose_email` or `clarify_email_body`
  That means the documented `session_context` system is absent.

- YouTube vs Spotify — where does platform detection fail?
  Failure starts in `intents/router.py` under the `play|put on` branch.
  Example: `play music on youtube`
  `_extract_platform()` correctly sees `youtube`, but the cleanup regex strips `play|put on|on|youtube|music|song`, leaving an empty or useless query.
  The branch then falls back to `spotify_play` with `song="music"`.
  Current behavior only works because `capabilities/planner.py` later overrides it with `play_youtube`.

- create_folder path — where does "on desktop" get parsed as name?
  There are two broken parsers.
  `intents/router.py` has a simplistic `([a-zA-Z0-9_\\-]+)` folder regex that turns `create folder on desktop` into `~/Developer/on`.
  `capabilities/resolver.py:resolve_folder_request()` has broader parsing, but it captures trailing location words into the folder name.
  Example:
  `create folder on desktop` -> `/Users/adityatiwari/Desktop/on desktop`
  `create folder called client work on desktop` -> `/Users/adityatiwari/Desktop/client work on desktop`

- open_terminal double open — where is the check missing?
  The missing check is in `executor/engine.py:open_terminal()`.
  It only checks `is_app_running("Terminal")`.
  It never checks whether Terminal already has a window or tab available before opening a new tab/window.
  `executor/app_state.py` already has `get_window_count()` and `get_terminal_tab_count()`, but `open_terminal()` does not use them.

# MEMORY FRAGMENTATION:
List all 7 memory write calls in _record()
There are more than 7 state mutations in `_record()`. The 7 persistent memory write systems are:
1. `b._bus_record(...)`
2. `b.add_to_working_memory(...)`
3. `b.record_episode_with_agentscope_feedback(...)`
4. `b.record_session(...)`
5. `b.save_session(...)`
6. `b.append_to_index(...)`
7. `b.record_project_execution(...)`

Also mutated on every turn, but not counted in the 7 above:
- `_remember_conversation_turn(...)`
- `b.analyze_and_learn(...)`
- `b.observe_project_relationships(...)`

Which ones are actually read back and used in prompts?
- `record_session(...)`
  Read back through `load_recent_sessions()` and `get_last_session_summary()`. Used in prompt/context paths.
- `save_session(...)`
  Used for persisted session snapshots and session summaries.
- `record_project_execution(...)`
  Feeds project history and project memory reads.
- `append_to_index(...)`
  Feeds layered memory / semantic recall helpers.
- `_remember_conversation_turn(...)`
  Used immediately by recent-dialogue prompt builders.
- `analyze_and_learn(...)`
  Read back by model/context learning paths.
- `observe_project_relationships(...)`
  Read by `brain/ollama_client._dependency_graph_context()`, but only on the `send_to_ollama()` path.

Which ones are write-only (data graveyard)?
- `add_to_working_memory(...)`
  No active production caller reads `get_full_context()` or `recall_fact()` back into the main pipeline.
- `record_episode_with_agentscope_feedback(...)`
  Writes RL data every turn, but does not feed user-facing prompts on the active path.
- `b._bus_record(...)`
  The bus writes every turn, but `memory.bus.recall()` has no active production callers.

# CURRENT ROUTING FLOW (trace exactly):
`"play music on youtube"` -> step by step -> final action
1. `pipeline/router.py:handle_input()` calls `early_intent = route(text)`
2. `intents/router.py` matches the `play|put on` branch
3. `_extract_platform()` identifies `youtube`
4. The YouTube cleanup regex strips `play`, `on`, `youtube`, `music`, `song`
5. The branch fails to produce a clean YouTube query
6. Router falls back to `Intent("spotify_play", {"song": "music"})`
7. `capabilities/planner.py:plan_semantic_task()` sees explicit `youtube` and returns `play_youtube`, `force_override=True`
8. `handle_input()` executes `_execute_semantic_task()` before lane routing
9. Final action becomes `open_url_in_browser` with a YouTube search URL
Breakage: deterministic routing is wrong; semantic override rescues it

`"create folder on desktop"` -> step by step -> where it breaks
1. `handle_input()` calls `early_intent = route(text)`
2. `intents/router.py` matches the simple folder regex
3. Deterministic route becomes `Intent("create_folder", {"path": "~/Developer/on"})`
4. `plan_semantic_task()` also runs and calls `resolve_folder_request()`
5. Resolver detects location `desktop`
6. Resolver incorrectly keeps `on desktop` as the folder name
7. Semantic task becomes `create_folder(path="/Users/adityatiwari/Desktop/on desktop")`, `force_override=True`
8. `_execute_semantic_task()` runs the semantic version
Final action: folder creation on Desktop with the wrong name
Breakage: both deterministic routing and semantic arg resolution parse location text as part of the name

`"latest news on claude"` -> step by step -> where it stops
1. `handle_input()` calls `early_intent = route(text)`
2. `intents/router.py` returns `Intent("news", {"topic": "claude", "hours": 24})`
3. `plan_semantic_task()` returns `lookup_news(topic="claude")`, `force_override=True`
4. `_execute_semantic_task()` runs before background-lane routing
5. `capabilities/registry.py` maps `lookup_news` to `run_agent(agent="news")`
6. Executor runs the news agent and records the result
It does not actually stop early; this is one of the few paths that reaches execution cleanly

`"write mail to vedang"` -> step by step -> where email dies
1. `handle_input()` calls `early_intent = route(text)`
2. `intents/router.py:_extract_compose_email_params()` returns `recipient="vedang"`, empty subject, empty body
3. Because `compose_email` is an instant-lane intent, `handle_input()` executes it immediately
4. `pipeline/router.py:_execute_instant()` sees missing subject/body and sets `_PENDING_DIALOGUE = {"kind": "pending_email", ...}`
5. Butler asks follow-up questions through `_resolve_pending_dialogue()`
6. Final compose action uses the literal recipient string `vedang`
Where it dies: contact normalization only handles spoken email formatting, not name-to-contact resolution, so Gmail compose opens without a real address unless the user says the actual email

`"what are my tasks today"` -> step by step -> why it fails
1. `handle_input()` calls `early_intent = route(text)`
2. `intents/router.py` does not match the exact `what are my tasks` shortcut because of the extra word `today`
3. Router falls through to generic `Intent("question")`
4. `plan_semantic_task()` sees a live-fact style question and returns `lookup_web(query="what are my tasks today")`
5. `handle_input()` reaches the `question` branch
6. `_execute_semantic_task()` runs `lookup_web`
7. `capabilities/registry.py` maps that to `run_agent(agent="search")`
Final behavior: it goes to live web lookup instead of the local task system
Breakage: exact-match task routing is too narrow, and semantic fallback sends it to the web

# CURRENT STATUS (2026-04-10)
- `executor/engine.py`
  Executor coverage now includes:
  app activation without double-opening Terminal
  folder/file CRUD
  browser window/back/refresh/go-to
  Gmail compose and WhatsApp compose
  volume/brightness/system toggles
  system info via local subprocess calls
  project opening with `claude -> codex -> cursor -> code` fallback
  page/video summary helpers
  task/calendar/VPS fallback handlers for routed local actions

- `intents/router.py`
  Deterministic routing now fixes the known folder parsing bug.
  Phrases like `create folder called client work on desktop` resolve to:
  `{"path": "~/Desktop", "name": "client work"}`
  Task queries like `what are my tasks today` now route to the local task system instead of web search.
  Classifier results now emit HUD events.

- `brain/session_context.py` + `pipeline/router.py`
  Pending follow-up state is now generalized instead of hardcoded to one-off globals.
  Multi-turn missing-parameter flows now use ordered pending slots:
  `ctx.set_pending(kind, data, required_fields)`
  Email subject/body follow-up now works through the shared session context.

- `brain/briefing.py` + `trigger.py`
  Startup briefing now lives in a dedicated module.
  Trigger sessions speak a short parallel-built briefing before STT starts on every session.

- `projects/dashboard.py` + frontend stream/events
  HUD event feed now keeps the last 100 events.
  New live WebSocket events are wired for:
  `pending_update`
  `mood_update`
  `memory_read`
  `classifier_result`
  `briefing_spoken`

- Validation
  Focused regression suite for router/executor/trigger/dashboard/runtime/pending/briefing passes.
  Full unittest discovery passes:
  `Ran 449 tests in 54.165s`

- Remaining verification gap
  Real voice-and-GUI smoke checks still need live manual confirmation for Chrome/Gmail/Terminal/Desktop side effects on the host machine.
