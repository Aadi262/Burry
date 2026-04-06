 ---
  BURRY HUD — Frontend Design + Backend Wiring Spec

  Where we stand right now

  Backend serves from projects/dashboard.py on 127.0.0.1:3333. It has:
  - SSE stream at /api/stream — pushes runtime_state.json every 350ms
  - WebSocket on port 3334 — partially implemented, unused by frontend
  - /api/command — accepts text commands, returns JSON
  - Static file serving for projects/frontend/

  runtime_state.json (written by runtime/telemetry.py) contains: state, last_heard_text, last_spoken_text, last_intent,
  workspace, active_tools, tool_stream, ambient_context, last_memory_recall, events, session_active.

  Frontend is one index.html + style.css + app.js (~1500 lines, no build step). It: renders a Three.js orb, polls SSE, shows
  panels on the left rail. The Three.js network is 200 random decorative nodes. Web Speech API is wired but Chrome-only and
  doesn't share history with the voice pipeline.

  The gap: The frontend shows what Burry said. It doesn't show what your Mac is actually doing. Gmail being open, Claude Code
  running, a failing test — none of that surfaces. The HUD is a log viewer with a pretty orb, not an operator dashboard.

  ---
  What needs to be built — Backend additions first

  New API endpoints needed in projects/dashboard.py:

  GET /api/runtime          → runtime_state.json (current, already exists as SSE)
  GET /api/projects         → projects/projects.json
  GET /api/tasks            → tasks/tasks.json
  GET /api/mac-activity     → memory/mac_state.json (open apps, frontmost, windows)
  GET /api/ambient          → last ambient bullets from runtime_state
  GET /api/events           → last 18 events from runtime_state
  GET /api/graph            → memory/layers/graph.json (project dependency graph)
  GET /api/vps              → pull VPS status via scripts/vps.py (cached 30s)
  POST /api/command         → already exists, accepts {text: "..."}
  POST /api/command/voice   → same pipeline as double-clap trigger, shares ConversationContext
  WS  /ws                   → replace SSE, push full state diffs on every telemetry write

  Critical wiring fix — POST /api/command/voice must go through the full butler pipeline. Right now /api/command is a shortcut.
  Text from the HUD needs to call butler.handle_input(text) and share the same ConversationContext object that the double-clap
  trigger uses. Otherwise HUD text and voice are two different conversations.

  GET /api/mac-activity needs to be live. context/mac_activity.py already writes to memory/mac_state.json every 30s. The
  dashboard just needs to serve that file. The mac_state.json has: frontmost_app, open_apps list, open_windows, focus_project,
  workspace_path.

  ---
  Frontend — New Layout Architecture

  Current layout problems:
  - Left rail has 5 stacked panels competing for vertical space
  - Center is just the orb with no information density
  - Right rail (bottom area) has transcript + command input but no real activity
  - No visual hierarchy — ambient bullets look the same as memory recall

  New layout — three columns, fixed topbar, command dock at bottom:

  ┌──────────────────────────────────────────────────────────────────┐
  │  TOPBAR: Brand · State Pill · Tool Pills · Mode Strip            │
  ├─────────────────┬────────────────────┬───────────────────────────┤
  │  LEFT RAIL      │   CENTER STAGE     │   RIGHT RAIL              │
  │                 │                    │                           │
  │  Mac Activity   │   Orb (3D)         │   Events Stream           │
  │  ─────────────  │                    │   ─────────────           │
  │  open apps      │   Project Graph    │   chronological feed      │
  │  + status dot   │   (below orb)      │   of every state/tool/    │
  │  + window name  │                    │   intent/memory event     │
  │                 │                    │                           │
  │  ─────────────  │                    │   ─────────────           │
  │  Workspace      │                    │   Pending Tasks           │
  │  focus project  │                    │   grouped by project      │
  │  active editor  │                    │                           │
  │                 │                    │   ─────────────           │
  │  ─────────────  │                    │   Memory Recall           │
  │  Ambient        │                    │   last semantic search    │
  │  3 bullets      │                    │   result                  │
  │                 │                    │                           │
  ├─────────────────┴────────────────────┴───────────────────────────┤
  │  COMMAND DOCK: [mic button]  [text input ─────────────] [send]   │
  │               Transcript line showing last heard / spoken        │
  └──────────────────────────────────────────────────────────────────┘

  ---
  Mac Activity Panel — the main new thing

  This is the critical panel. Pull from /api/mac-activity (refreshes every 10s via polling or WebSocket push).

  What to render per open app:

  ● Gmail            [browser]    • 3 tabs open
  ● Claude Code      [editor]     • mac-butler workspace
  ● Cursor           [editor]     • email-infra workspace
  ● Spotify          [music]      • ▶ playing
  ● Terminal         [shell]      • 2 windows

  Each app entry:
  - Status dot: green = frontmost, blue = active, grey = background
  - App name: display name from open_apps list
  - Category badge: [browser] [editor] [music] [shell] [tool] — inferred from app name mapping
  - Context line: for editors — which workspace is open (from mac_state.json). For browser — tab count or last URL domain. For
  music — now playing.

  App → category mapping (frontend only, no backend change needed):
  const APP_CATEGORIES = {
    "Google Chrome": "browser", "Safari": "browser", "Firefox": "browser",
    "Cursor": "editor", "Visual Studio Code": "editor",
    "Terminal": "shell", "iTerm2": "shell",
    "Spotify": "music",
    "Claude": "ai", "ChatGPT": "ai",
    "Slack": "comms", "Discord": "comms", "Telegram": "comms",
    "Figma": "design", "Sketch": "design",
    "TablePlus": "data", "Postico": "data",
    "Obsidian": "notes",
  }

  Frontmost app gets highlighted — the card with focus_project field matching gets a left border in --accent.

  ---
  Project Dependency Graph — replace the decorative Three.js network

  The existing memory/layers/graph.json has edges with from, to, type (depends_on, shares_resource, blocked_by). Pull from
  /api/graph.

  Replace the random 200-node network with a real force-directed graph:

  - Nodes = projects from /api/projects
  - Edges = dependency edges from /api/graph
  - Node color by status: active = --accent, paused = --cobalt, blocked = --danger, done = --success
  - Edge color by type: depends_on = --cobalt, blocked_by = --danger, shares_resource = --violet
  - Node size proportional to number of active tasks
  - On hover: show project name, status, next task, blockers
  - On click: expand a detail card in the center stage with full project info

  If the graph has no edges yet (empty graph.json), show the projects as standalone nodes — still meaningful, still real data.

  Keep the orb above the graph. Orb takes top 55% of center stage, graph takes bottom 45%.

  ---
  Events Stream — right rail, replace the event track

  Currently the event track is a small strip. Expand it to a full scrolling feed.

  Pull from runtime_state.events (last 18 events, each has at, kind, message, meta).

  Render each event as a timestamped row with kind badge:

  14:32  [heard]    "open mac-butler in cursor"
  14:32  [intent]   open_project  conf: 0.95
  14:32  [tool]     open_editor · running
  14:32  [tool]     open_editor · ok
  14:33  [ambient]  Ambient context refreshed
  14:35  [memory]   Recalled 2 matches for "auth system"
  14:35  [agent]    search · Bitcoin price → $94,200

  Color each kind: heard = --text-faint, intent = --accent, tool = --cobalt, state = --amber, memory = --violet, agent =
  --success, ambient = --text-faint.

  This replaces the current event track and gives you a real audit trail of everything Burry did in the session.

  ---
  Command Dock — fix the two-path problem

  The command input needs one path to the full butler pipeline.

  How it must work:
  1. User types in [command-input] and presses Enter or clicks send
  2. Frontend sends POST /api/command with { "text": "...", "source": "hud" }
  3. Backend routes through the same handle_input() function that the double-clap trigger uses
  4. ConversationContext is shared — so HUD text + voice clap are one conversation
  5. Response streams back via WebSocket or SSE — the event stream updates, the state pill changes, TTS fires on the Mac

  Mic button in the command dock: pressing it should activate the backend's voice listener (listen_continuous()) for one turn,
  not the browser's SpeechRecognition. Send POST /api/command with { "action": "listen_once" }. The backend listens, transcribes
  with Whisper, runs through pipeline, result appears in the event stream.

  Drop browser SpeechRecognition entirely — it creates a parallel STT path that bypasses Whisper, bypasses the conversation
  context, and only works on Chrome.

  ---
  Transcript — minimal, not a panel

  The transcript should be two lines at the bottom of the command dock, not a scrolling panel:

  You said:    "open mac-butler, run the tests"
  Burry said:  "Opening mac-butler in Cursor. Tests are running."

  These update live from runtime_state.last_heard_text and runtime_state.last_spoken_text. No scroll needed — the events feed is
  the scroll.

  ---
  Design system refinements

  State-aware body color is already in CSS. Extend it so panels subtly pulse on state change:

  .panel {
    transition: border-color 0.4s ease, box-shadow 0.4s ease;
  }
  body[data-state="thinking"] .panel {
    border-color: rgba(255, 170, 0, 0.35);
  }
  body[data-state="speaking"] .panel {
    border-color: rgba(232, 244, 255, 0.25);
  }

  App status dots should use the correct color per category:
  - editor = --accent (cyan)
  - browser = --cobalt (blue)
  - music = --violet (purple)
  - shell = --amber (amber)
  - ai = --success (green)
  - comms = --text-faint (grey)

  Typography scale — add these to :root:
  --font-label: 9px;       /* panel headers */
  --font-meta: 10px;       /* timestamps, badges */
  --font-body: 12px;       /* content rows */
  --font-strong: 13px;     /* workspace values, app names */
  --font-headline: 15px;   /* state pill, project names */

  Panel scroll — all panels should have overflow-y: auto with a thin scrollbar. Currently the left rail overflows without
  scrolling.

  Keyboard shortcuts (add to app.js):
  - / → focus command input
  - Escape → blur command input
  - 1, 2, 3 → switch mode tabs (mood / session / state)
  - Ctrl+Enter → submit command

  ---
  WebSocket instead of SSE

  Switch from SSE polling to a single persistent WebSocket connection. dashboard.py already has _WS_LOOP set up — it just needs
  to be activated.

  Frontend WebSocket logic:
  function connectWS() {
    const ws = new WebSocket("ws://127.0.0.1:3334");
    ws.onmessage = (event) => {
      const state = JSON.parse(event.data);
      updateAllPanels(state);
    };
    ws.onclose = () => {
      showOfflineBanner();
      setTimeout(connectWS, 3000); // reconnect
    };
  }

  Offline banner — when WebSocket closes, show a banner across the top: BURRY OFFLINE · Attempting to reconnect... in --danger
  color. Remove it when reconnected.

  ---
  App.js split — tell Codex to break it into modules

  projects/frontend/
    index.html          (no change to structure)
    style.css           (extend with new rules above)
    modules/
      orb.js            (Three.js orb, state color, bloom)
      graph.js          (project dependency force graph)
      stream.js         (WebSocket connection, state dispatch)
      panels.js         (all DOM update functions for each panel)
      mac-activity.js   (Mac Activity panel logic + category mapping)
      events.js         (Events stream rendering)
      commands.js       (command dock, keyboard shortcuts)
    app.js              (thin orchestrator — imports modules, wires them)

  Use ES modules with import/export. The existing importmap in index.html already supports this pattern.

  ---
  Summary of wiring — the complete data flow

  ┌──────────────────┬──────────────────────────────────────────────────┬──────────────────┬───────────────────────────┐
  │  Frontend Panel  │                   Data Source                    │ Update Frequency │      Backend Module       │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ State Pill       │ runtime_state.state                              │ WebSocket push   │ runtime/telemetry.py      │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Tool Pills       │ runtime_state.active_tools                       │ WebSocket push   │ runtime/telemetry.py      │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Mac Activity     │ /api/mac-activity                                │ Poll 10s         │ context/mac_activity.py   │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Workspace        │ runtime_state.workspace                          │ WebSocket push   │ runtime/telemetry.py      │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Ambient Bullets  │ runtime_state.ambient_context                    │ WebSocket push   │ daemons/ambient.py        │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Memory Recall    │ runtime_state.last_memory_recall                 │ WebSocket push   │ runtime/telemetry.py      │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Events Stream    │ runtime_state.events                             │ WebSocket push   │ runtime/telemetry.py      │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Pending Tasks    │ /api/tasks                                       │ Poll 30s         │ tasks/task_store.py       │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Project Graph    │ /api/graph                                       │ Poll 60s         │ memory/graph.py           │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Projects (nodes) │ /api/projects                                    │ Poll 60s         │ projects/project_store.py │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Transcript       │ runtime_state.last_heard_text / last_spoken_text │ WebSocket push   │ runtime/telemetry.py      │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ VPS Chip         │ /api/vps                                         │ Poll 30s         │ scripts/vps.py            │
  ├──────────────────┼──────────────────────────────────────────────────┼──────────────────┼───────────────────────────┤
  │ Command Submit   │ POST /api/command → butler.handle_input()        │ On user action   │ butler.py                 │
  └──────────────────┴──────────────────────────────────────────────────┴──────────────────┴───────────────────────────┘

  Burry OS — Complete Codebase Analysis

  Architecture Overview

  Voice Pipeline:  Trigger → STT → Intent Router → Executor → [LLM] → TTS
  Background:      Heartbeat / BugHunter / Ambient / MacWatcher (all
  threaded)
  HUD:             Python HTTP server → SSE stream → Vanilla JS +
  Three.js
  Memory:          Layered (MEMORY.md index / project files / session
  JSONL)
  Context:         Git + VSCode + macOS Activity + Obsidian + VPS + MCP +
   Tasks

  ---
  Consistency Problems (fix these first)

  1. Two daemon directories — daemon/ vs daemons/
  daemon/ has heartbeat, bug_hunter, clap_detector. daemons/ has ambient.
   One directory, one convention.

  2. HEARTBEAT_ENABLED and BUG_HUNTER_ENABLED defined twice
  Declared in butler_config.py AND re-declared at the top of
  daemon/heartbeat.py and daemon/bug_hunter.py. The daemon files override
   config silently.

  3. _clip / _clip_text / _compress copied across 7+ files
  memory/layered.py, runtime/telemetry.py, daemons/ambient.py,
  memory/store.py, brain/ollama_client.py, browser/agent.py,
  executor/engine.py each define their own version. Should live in one
  utils.py.

  4. WEB_APP_URLS in executor/engine.py duplicates APP_MAP in
  intents/router.py
  Same URLs defined in two places. If you update one, the other drifts.

  5. IntentResult and Intent both exist in intents/router.py
  Intent class has a to_action() method. IntentResult is the return type
  used in butler.py. Looks like a migration that never finished cleaning
  up.

  6. PROJECT_MAP in intents/router.py is hardcoded, not synced with
  project_store.py
  Add a project via the project store → intent router still can't find it
   by name. These need to stay in sync or the router should query the
  store.

  7. identity/__init__.py is completely empty
  The module exists but is hollow. Either fill it or remove it.

  ---
  Backend Gaps

  8. memory/learner.py only has 3 hardcoded pattern rules
  The learner only fires on: Cursor + music combo, late night sessions,
  opened folders. It never learns from failed intents ("user said X,
  Butler replied nothing"), never learns from corrected intent flows,
  never learns which LLM model performed well on which task type.

  9. memory/graph.py has zero automatic writers
  The dependency graph (depends_on, shares_resource, blocked_by) is read
  in ollama_client.py for context but nothing ever writes to it
  automatically. You have to manually construct edges. The system that's
  supposed to reason about cross-project dependencies has an empty graph.

  10. _installed_models cache in agents/runner.py never refreshes
  Set once at process start, never TTL'd. Install a new Ollama model
  while Butler runs → agents still think it's not available.

  11. context/__init__.py calls sync_from_todo_md() on every context
  build
  That's a disk read + write side-effect on the hot path. Every heartbeat
   tick, every voice trigger, every agent call rebuilds context and syncs
   from todo.md. Should be event-driven or on a timer.

  12. brain/tools.py — only 5 tools exposed to the LLM tool-calling path
  open_project, run_shell, browse_web, recall_memory,
  take_screenshot_and_describe. The executor can do: git commit, spotify,
   notifications, obsidian notes, ssh, docker, open apps, set reminders.
  None of those are in the tool schema so the LLM can't plan to use them
  via tool-calling.

  13. Confirmation UI blocks on stdin
  executor/engine.py's _ask_confirmation() probably calls input(). When
  Butler runs headless (double-clap trigger, no terminal),
  REQUIRE_CONFIRMATION_FOR_PUSH = True will hang the pipeline silently.

  14. EXA_API_KEY hardcoded in butler_config.py
  EXA_API_KEY = "move-to-local-secrets"
  This is a real key sitting in a tracked config file. Should be in
  butler_secrets/local_secrets.json alongside the other secrets.

  15. ConversationContext.turns is in-memory only
  6 turns stored in a Python object. If the process crashes mid-session,
  all conversation history is gone. runtime_state.json already stores
  last_heard_text and last_spoken_text — the full turns list should live
  there too.

  16. MAX_SPEECH_S = 8.0 hardcoded in voice/stt.py, not in
  butler_config.py
  You can't tell Butler to listen longer without editing source. Same
  with SILENCE_THRESHOLD, MIN_SPEECH_S. These should be in config.

  17. task_store.py hardcodes project names for priority
  for project in ("mac-butler", "email-infra"):
  Third project added → task priority doesn't work unless you edit
  source.

  18. No circuit breaker on LLM calls
  When Ollama is unreachable or the model is loading, calls time out
  after 45s. No fast-fail, no retry with a different model in the chain,
  no "butler is thinking" notification to TTS while waiting. The pipeline
   just silently blocks.

  19. SearXNG availability check runs once at startup, never re-checked
  _SEARCH_CHECKED = True after first check. If SearXNG starts mid-session
   (you restart Docker), Butler doesn't know and keeps falling back to
  Exa.

  ---
  Frontend Gaps

  20. Three.js loaded from CDN (unpkg.com)
  No offline operation. First load requires internet. Should be locally
  bundled or at least have a local fallback.

  21. app.js is one ~1500-line file with zero separation
  3D orb rendering, SSE stream handling, Web Speech API, DOM updates,
  WebSocket logic, project card rendering — all mixed together. Should be
   split into: orb.js, stream.js, panels.js, speech.js, ui.js.

  22. Browser SpeechRecognition in the HUD creates a parallel STT path
  The HUD has SpeechRecognition (Chrome-only). The backend has Whisper
  (MLX / faster-whisper). These two paths don't share context. If you use
   the HUD mic button, does it go through the same pipeline as
  double-clap? Unclear.

  23. The Three.js network graph is purely decorative — 200 random nodes
  memory/graph.py has a real dependency graph. The HUD should visualize
  it. Right now 200 random orbiting particles have nothing to do with
  actual project data.

  24. No keyboard shortcuts
  No Ctrl+Enter to submit, no / to focus command input, no number keys to
   switch panels. All mouse-only for panel navigation.

  25. No offline / backend-down state in the HUD
  When the SSE stream dies (Python server not running), the HUD shows
  stale data forever with no indicator. Should show a "Burry offline"
  banner.

  26. Text commands from HUD vs voice commands go through different code
  paths
  HUD sends to /api/command. Voice goes through butler.py's full
  pipeline. They don't share the ConversationContext so HUD text input
  doesn't have voice history and vice versa.

  27. focusKind panel state resets on page refresh
  Lost on every reload. Should persist in localStorage.

  ---
  Features Worth Adding

  28. Wake word activation as a third trigger
  Double-clap is clever but impractical at a quiet desk. A keyword
  spotter ("hey Burry") using openWakeWord or Porcupine as a third
  activation path alongside clap and keyboard would cover all scenarios.

  29. Shell output → voice summary
  When run_shell executes tests or builds, the output is captured but
  never spoken. "Ran tests: 3 passed, 1 failed, 2 errors in auth.py"
  would close the loop. The LLM already has the shell output in the
  executor result.

  30. Git diff → commit message generation
  git_commit intent exists but executes a raw commit. Butler has the LLM
  right there. Have it: git diff --cached → LLM → suggest message → user
  confirms → commit. One tool call.

  31. Calendar/schedule awareness in heartbeat
  The KAIROS heartbeat checks work context but has no concept of
  time-boxed events. Reading macOS Calendar (AppleScript) and injecting
  "meeting in 20 minutes" into the heartbeat context would make it
  meaningfully proactive.

  32. Spotify "what's playing" intent
  Play/pause/next/prev/volume are handled. "What's this song?" is not.
  One AppleScript call to Spotify and speak the track name.

  33. Auto-populate the memory graph
  When the same two projects appear in context within the same session
  window, write a shares_resource edge. When a project has a blocker that
   mentions another project name, write a blocked_by edge. The graph
  infrastructure exists — it just needs writers.

  34. Per-project context injection on open_project
  When Butler opens a project, automatically load that project's Layer 2
  memory file and inject it into the next LLM call. Right now you have to
   explicitly ask "what do I know about mac-butler".

  35. Session end → Obsidian summary
  On session close, generate a 3-bullet "what happened today" from the
  session JSONL and write it to Obsidian under Daily/YYYY-MM-DD.md. The
  vault loader and obsidian note executor action already exist.

  36. VPS metrics on the HUD
  The VPS context is pulled once per context build via SSH. Add a
  /api/vps-metrics endpoint that streams CPU/memory/disk every 30s to the
   HUD Runtime panel, replacing the static "Contabo VPS" chip.

  ---
  Summary by Priority

  ┌─────────────────────────────────────────┬───────┐
  │                Category                 │ Count │
  ├─────────────────────────────────────────┼───────┤
  │ Consistency fixes (naming, duplication) │ 7     │
  ├─────────────────────────────────────────┼───────┤
  │ Backend gaps (bugs/missing behavior)    │ 12    │
  ├─────────────────────────────────────────┼───────┤
  │ Frontend gaps                           │ 8     │
  ├─────────────────────────────────────────┼───────┤
  │ New features                            │ 9     │
  └─────────────────────────────────────────┴───────┘

  The most impactful single fix: #12 (expand the tool schema) — the LLM
  tool-calling path is severely underutilized because it can only see 5
  tools out of the 30+ things Butler can actually do.

  The biggest structural smell: #3 (cloned utility functions across 7
  files) and #21 (monolithic app.js) — both indicate the codebase needs a
   thin shared utils.py and a JS module split before it grows harder to
  navigate.
