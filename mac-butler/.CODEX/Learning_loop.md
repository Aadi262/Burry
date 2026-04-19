## BURRY OS — Learning Loop
Every mistake gets logged here so it NEVER happens again.
Codex MUST read this before every session.
Codex MUST append to this after every session.

## HOW TO USE THIS FILE
Before every session:
Read all entries under MISTAKES NEVER REPEAT
Read all entries under ROOT CAUSES
Apply lessons before writing code
After every session:
If something broke — add it under MISTAKES NEVER REPEAT
If something took too long to debug — add it under HARD LESSONS
If a test revealed a real bug — add it under TEST INSIGHTS

## MISTAKES NEVER REPEAT
## MISTAKE 001 — LLM inside a hook caused 70 second responses
Date: Apr 2026
What happened:
pre_reply_hook called get_compressed_context() which called the LLM
This happened BEFORE every AgentScope turn
Result: every greeting took 61.9 seconds instead of 7.9 seconds
Root cause:
Developer misread "inject memory before reply" as
"inject memory inside the pre_reply hook"
Hooks fire synchronously before every LLM call
Calling LLM inside hook = 2x LLM calls minimum
The fix:
Removed LLM call from pre_reply_hook
Made _ws_broadcast fire-and-forget in background thread
Moved memory injection to before agent is called, not inside hook
Rule added:
NEVER call LLM inside a hook
Hooks are for: WS broadcast, logging, state updates ONLY
Verification:
grep -n "_call|get_compressed" brain/agentscope_backbone.py | grep -i hook
→ must return nothing
## MISTAKE 002 — secrets/init.py shadowed Python stdlib secrets module
Date: Apr 2026
What happened:
A file named secrets/init.py existed in the repo
Python's edge-tts library calls secrets.token_hex() from stdlib
Python found OUR secrets file first instead of stdlib
Edge TTS failed silently on every call
Butler fell back to Kokoro every single time
Root cause:
Never name a folder or file the same as a Python stdlib module
Python searches local directories before stdlib
The fix:
Renamed secrets/init.py to butler_secrets/init.py
Updated all imports
Rule added:
Never create a file or folder named after a Python stdlib module
(secrets, json, os, sys, re, time, math, etc)
Verification:
venv/bin/python -c "import secrets; print(secrets.token_hex(16))"
→ must print hex string with no error
## MISTAKE 003 — asyncio.run() inside AgentScope tool caused crashes
Date: Apr 2026
What happened:
planner_agent.py and research_agent.py called asyncio.run()
AgentScope tools already run inside an async event loop
asyncio.run() inside a running loop = RuntimeError
Agent calls crashed silently
Root cause:
asyncio.run() creates a NEW event loop
If called from inside a running loop it raises RuntimeError
AgentScope runs everything in its persistent loop
The fix:
Replaced asyncio.run() with concurrent.futures.ThreadPoolExecutor
Background tasks dispatched to thread pool instead
Rule added:
NEVER use asyncio.run() inside any AgentScope tool or agent
Use ThreadPoolExecutor for background async work instead
MISTAKE 004 — agentscope.init() called multiple times caused race conditions
Date: Apr 2026
What happened:
Multiple files were calling agentscope.init()
AgentScope init is a global singleton
Multiple calls caused race conditions on the init name
Agent names collided causing silent failures
Root cause:
No guard on agentscope.init()
Each module thought it was responsible for initializing
The fix:
Created ensure_agentscope_initialized() in agentscope_backbone.py
This function uses a flag to call init only once
All other files removed their agentscope.init() calls
Rule added:
Only brain/agentscope_backbone.py calls agentscope.init()
All other files call ensure_agentscope_initialized() instead
MISTAKE 005 — _record() made 9 synchronous disk writes per command
Date: Apr 2026
What happened:
_record() in pipeline/recorder.py wrote to 6+ JSON files
Every single command triggered 9 synchronous writes
With dashboard polling at 120ms this caused disk contention
Commands felt slow even when LLM was fast
Root cause:
Feature creep — each sprint added another write without removing old ones
No single write path was enforced
The fix:
Created memory/bus.py with batched JSONL appends
_record() now calls memory_bus.record() once
Bus flushes every 2 seconds in background thread
Rule added:
Only memory/bus.py writes to disk on the hot path
All other memory systems update in background only
MISTAKE 006 — "on desktop" included in folder name
Date: Apr 2026
What happened:
User says "create folder on desktop called Work"
Router extracted full text as folder name
Result: folder named "on desktop called Work" created in wrong location
Root cause:
Regex extracted everything after "folder" as the name
Did not separate location keywords from name keywords
The fix:
Strip location keywords before extracting name
LOCATIONS = {"on desktop": "~/Desktop", "in documents": "~/Documents" ...}
Strip match from text, use remainder as name
Rule added:
Always separate location words from name words before creating folders
Default path is always ~/Desktop if no location specified
MISTAKE 007 — Terminal opened twice on repeated "open terminal" command
### MISTAKE 08 — Never mentioned LEARNING_LOOP.md to Codex
Date: Apr 2026
What happened:
  LEARNING_LOOP.md was created but never told to Codex
  Codex never read it, never updated it
  The learning loop was completely bypassed
Root cause:
  Rules files existed but no master index told Codex
  to read them all at the start of every session
The fix:
  Created .claude/README.md as master index
  First line says READ THIS FIRST
  Lists LEARNING_LOOP.md in required reading order
Rule added:
  Every session must start with:
  "Read .claude/README.md first"
  That file tells you what else to read

### MISTAKE 09 — 30+ if statements in executor dispatcher
Date: Apr 2026
What happened:
  Added 30+ if t == "action": return self.action()
  One per action type, sprawling and hard to extend
Root cause:
  No pattern specified for dispatcher architecture
The fix:
  Use dispatch table dict instead
  table = {"volume_up": lambda: self.volume_up(), ...}
  if t in table: return table[t]()
Rule added:
  NEVER use if chains for dispatchers
  ALWAYS use dispatch table dict
  Adding new action = one line in table
Date: Apr 2026
What happened:
User said "open terminal"
Executor ran subprocess.run(["open", "-a", "Terminal"])
If Terminal already running: opened a new window anyway
Result: two terminal windows every time
Root cause:
No check if app was already running before opening
The fix:
Check via osascript if app is already running
If running: activate existing window
If not: open new
Rule added:
For SINGLE_INSTANCE_APPS (Terminal, iTerm, etc)
Always check if running before opening
SINGLE_INSTANCE_APPS = ["Terminal", "iTerm2", "Finder"]
MISTAKE 008 — "play X on youtube" routed to Spotify
Date: Apr 2026
What happened:
User says "play blinding lights on youtube"
Router matched "play" → spotify_play intent
YouTube keyword ignored completely
Spotify opened instead
Root cause:
Intent router checked for "play" keyword first
Platform keyword check came after intent was already decided
The fix:
Check platform keyword BEFORE deciding intent
if "youtube" in text → open YouTube search URL
if "spotify" in text or no platform → use Spotify
Rule added:
Platform detection must happen BEFORE intent routing for music
Never assume default platform without checking text first
MISTAKE 009 — Dashboard polling every 120ms caused disk storm
Date: Apr 2026
What happened:
_watch_operator_state() polled every 120ms
Each poll read runtime_state.json, mac_state.json, tasks.json
Also made HTTP request to check SearXNG availability
8 disk reads + 1 HTTP request per second constantly
Even when no one was looking at the dashboard
Root cause:
No event-driven updates
Pure polling loop with no backoff
The fix:
Changed sleep to 500ms (4x less polling)
Removed SearXNG HTTP check from polling loop
SearXNG status cached at startup only
Rule added:
Dashboard poll interval minimum 500ms
Never make HTTP requests inside the polling loop
Cache external service status, do not check every poll
MISTAKE 010 — Too many files added without connecting them
Date: Apr 2026
What happened:
brain/mood_engine.py existed for weeks
skills/email_skill.py existed but was never called
brain/session_context.py existed but was never imported in trigger.py
80+ Python files but core pipeline still broken
Root cause:
Every sprint added new files
No sprint was dedicated to wiring existing files

## MISTAKE 011 — deterministic casual replies were running after semantic planning
Date: Apr 2026
What happened:
User said "thank you"
pipeline/router.py still built a semantic task before the deterministic casual shortcut fired
Result: a trivial reply could wait on the planner path and blow the instant-lane timing budget
Root cause:
Fast-path ordering drifted while unknown/planner logic was being hardened
The fix:
Move `_DETERMINISTIC_CASUAL_RESPONSES` ahead of `plan_semantic_task(...)`
Add a regression that casual replies never call semantic planning
Rule added:
Casual acknowledgements and other zero-work replies must return before any planner or live-lookup path is considered

## MISTAKE 012 — host smoke checks used confirmation-gated actions and brittle one-line Python control flow
Date: Apr 2026
What happened:
The first Phase 1 host smoke harness used overwrite/delete style checks and complex `python -c` snippets
Result:
filesystem smoke hit the repo confirmation gate
calendar smoke tripped over inline control-flow syntax
debugging the harness took longer than the feature verification
Root cause:
The harness was optimized for quick implementation instead of matching the repo's execution boundaries
The fix:
Move filesystem and calendar smoke checks into explicit helper functions
Avoid destructive or confirmation-gated actions in default host smoke
Use explicit operator-gated skips for real send flows
Rule added:
Smoke harnesses must exercise safe, verification-friendly actions by default and treat destructive or delivery checks as opt-in

## MISTAKE 013 — raw Calendar automation failures leaked into user-facing output
Date: Apr 2026
What happened:
Calendar reads surfaced raw `osascript` / JXA errors like `syntax error`, `parameter is missing`, or timeouts
Result:
The product lied less than before, but it still exposed implementation garbage instead of a clear host requirement
Root cause:
The executor treated all Calendar scripting failures as generic command output

## MISTAKE 014 — new host smoke must be self-contained and local-first
Date: Apr 2026
What happened:
The first Phase 3A host smoke reused public `example.*` browser targets, fuzzy filesystem source names, and an untested AppleScript date string
Result:
browser smoke opened public test pages, move verification picked the wrong source, and Calendar add failed on the real host
Root cause:
The harness and automation strings were written before validating them against the actual machine behavior
The fix:
Use local temp `file://` pages for browser smoke
Use explicit filesystem paths when the verifier depends on exact source removal
Test the exact host-accepted AppleScript date format before making it the default automation string
Rule added:
Every new host smoke path should be self-contained, local-first, and explicit
Any OS parser or automation string must be verified on the host before it becomes the default runtime path
The fix:
Normalize Calendar automation failures into one explicit message:
`Calendar read is unavailable until Calendar automation access is granted on this host.`
Rule added:
Host permission failures must surface as clear degraded-state messages, never raw automation stack noise
No rule enforced "wire before you build"
The fix:
Session 1 dedicated entirely to wiring existing files
No new features until existing ones are connected
Added rule to CODEX_RULES.md
Rule added:
Before creating any new file grep for it in existing files
Wire before you build
Never add a feature without connecting it end to end

HARD LESSONS (took a long time to debug)
LESSON 001 — agentscope.agents module does not exist in current package
What: agentscope.agents has no BrowserAgent or DeepResearchAgent
How long to debug: 2 hours across multiple sessions
Resolution: Build custom fallbacks. Do NOT try to import from agentscope.agents.
Remember: Check pip show agentscope before assuming any submodule exists
LESSON 002 — Kokoro TTS voice path was broken by secrets module clash
What: Every TTS call silently fell back to Kokoro
How long to debug: Several sessions
Resolution: The secrets folder shadowed Python stdlib. Rename to butler_secrets.
Remember: Never name folders after Python stdlib modules
LESSON 003 — Local Ollama uses 127.0.0.1 not localhost on some systems
What: Ollama connection refused intermittently
Resolution: Use 127.0.0.1 explicitly. localhost resolves to IPv6 on some Macs.
Remember: OLLAMA_LOCAL_URL = "http://127.0.0.1:11434" always
LESSON 004 — nomic-embed-text evicts the main LLM from VRAM
What: Every recall_memory call added 3-5 seconds
How long to debug: Not noticed for weeks
Resolution: Add embedding cache (md5 hash, max 500 entries)
Remember: Embedding calls must be cached. Never call Ollama embedding per command.
LESSON 005 — SearXNG JSON output requires manual settings.yml change
What: SearXNG returned 403 for JSON format requests
Resolution: Add formats: [html, json] to docker/searxng/settings.yml
Remember: The default SearXNG Docker image only enables HTML. Always mount the settings file.

TEST INSIGHTS (real tests that caught real bugs)
INSIGHT 001 — test_create_folder_correct_path caught the name bug
Test: create_folder with "on desktop" in text
Expected: ~/Desktop/WorkFolder
Got: folder named "WorkFolder on desktop" in wrong location

### MISTAKE 011 — Wrote roadmap docs before reading the repo master index
Date: Apr 2026
What happened:
A new phase tracker was drafted from audits and sprint docs first.
The repo master index and required `.CODEX` reading set were not checked before writing.
Result:
The first version of the roadmap missed repo-specific constraints like:
single-owner module boundaries,
`memory/bus.py` as the only hot-path write path,
`brain/tools_registry.py` as the only tool registry,
and the existing capability-ID scheme in `Capability_Map.md`.
Root cause:
Started from general repo docs instead of the session bootstrap docs that define local rules.
Also trusted the user path wording instead of verifying the actual doc folder on disk.
The fix:
Read `Codex.md`, `AGENTS.md`, `Codex_Rules.md`, `Learning_loop.md`, `SPRINT_LOG.md`, and `Capability_Map.md` before editing planning docs.
Re-aligned `docs/phases/PHASE.md` to the actual `.CODEX` conventions.
Rule added:
Before writing any roadmap, phase, or architecture doc, verify the repo's master index and required session docs on disk first.
Verification:
`find mac-butler/.CODEX -maxdepth 1 -type f | sort`
must be checked before claiming the repo has no Codex session docs
Action: Fixed location keyword stripping in intents/router.py
INSIGHT 002 — test_greeting_under_8_seconds caught the hook regression
Test: time butler.py --command 'hi'
Expected: under 8 seconds
Got: 61.9 seconds
Action: Found LLM call inside pre_reply_hook. Removed it.
INSIGHT 003 — test_open_app_terminal_no_duplicate caught double-open
Test: call open_app Terminal twice, count windows
Expected: same count before and after
Got: count increased by 1 every call
Action: Added osascript running check before opening
INSIGHT 004 — test_no_unknown_for_natural_language is the most important test
Test: run butler with "yo what is happening in india today"
Expected: real news spoken
Got: "I didn't catch that. Say open, search..."
Status: STILL FAILING — this is the core routing problem
Action needed: Wire gemma4:e4b as primary classifier

TEMPLATE FOR NEW ENTRIES
MISTAKE XXX — [short description]
Date: [date]
What happened:
[what the user experienced]
Root cause:
[why it happened technically]
The fix:
[what was changed]
Rule added:
[what rule prevents this forever]
Verification:
[how to verify the fix worked]

CODEX MUST DO AT END OF EVERY SESSION
Append to this file under the correct section:

Every mistake made this session → MISTAKES NEVER REPEAT
Every thing that took >30 min to debug → HARD LESSONS
Every test that caught a real bug → TEST INSIGHTS

Command to append from session:
echo "### MISTAKE XXX — description" >> .claude/LEARNING_LOOP.md
This file is the institutional memory of Burry OS.
Every entry makes the next session faster.
Never delete entries. Only add them.

MISTAKE 005 — HUD was executing Butler locally instead of hitting the live backend
Date: 2026-04-11
What happened:
The dashboard looked alive, but typed commands, mic capture, and interrupt were running inside `projects/dashboard.py` via local `butler` imports instead of going through the live backend process.
Root cause:
The HUD API paths called `handle_input()` and `interrupt_burry()` directly in the dashboard process. This created split-brain behavior between the HUD and the actual backend on port `3335`.
The fix:
Dashboard command, mic, and interrupt paths now proxy to backend HTTP endpoints on `3335`, and `channels/a2a_server.py` now exposes `/api/v1/health`, `/api/v1/run`, `/api/v1/listen_once`, and `/api/v1/interrupt`.
Rule added:
If the HUD and backend are separate processes, the HUD must never import live execution entrypoints directly. It must proxy to the backend.
Verification:
`/api/v1/command` on `3333` now reaches `/api/v1/run` on `3335`, and `/api/v1/command {action:listen_once}` now reaches backend `listen_once`.

MISTAKE 006 — fresh launch was polluted by stale runtime and session memory
Date: 2026-04-11
What happened:
The HUD kept showing old heard/spoken state and Burry could start a new launch with stale session memory and stale dashboard state mixed into the new run.
Root cause:
`butler.py` did not reset runtime telemetry on startup, and AgentScope session restore happened before any fresh-launch guard.
The fix:
Added runtime reset on fresh launch, disabled session restore for live launches, and added backbone session reset before starting a new live session.
Rule added:
Every live launch path must reset transient runtime state before starting STT or speaking the startup briefing.
Verification:
Fresh launch moved `last_reset_at`, cleared stale `last_heard_text`, `last_intent`, `turns`, and started the new session from a clean runtime snapshot.

### MISTAKE 015 — passive backend launch cannot auto-enter STT or allow duplicate owners
Date: 2026-04-18
What happened:
Plain `butler.py` startup still auto-entered interactive STT, and a second long-lived Butler process could start at the same time.
Result:
Two voice runtimes could speak in parallel, audio would crackle, and the HUD/runtime state no longer represented a single truthful owner.
Root cause:
Wake ownership was split between the documented `trigger.py` path and the default `butler.py` path, and there was no long-lived runtime lock at process startup.
The fix:
Make default `butler.py` startup passive standby, keep briefing and STT behind explicit trigger or HUD/API activation, hold a live-runtime file lock so duplicate backends refuse to start, and add clap startup arming plus active-session suppression so standby does not self-wake from launch noise.
Rule added:
Long-lived voice or backend launch paths must be singleton-guarded and must not auto-speak unless the user explicitly activated a session.

### MISTAKE 016 — live wake behavior needs an explicit operator mode, not an implied default
Date: 2026-04-18
What happened:
The runtime had passive standby, but there was no direct way to request clap-only wake for a live session and no clean way to move the HUD off the default localhost port during operator testing.
Result:
Live testing was forced through the default `3333/3334/3335` ports and the wake-word path stayed armed even when the operator wanted clap-only behavior.
Root cause:
The runtime shape was configurable in code, but not exposed through the entrypoint contract used during real local testing.
The fix:
Expose HUD port selection through environment variables and expose clap-only standby through `butler.py --clap-only`.
Rule added:
Any runtime mode needed for real host verification should be selectable from the supported entrypoints, not hidden behind a code edit.

### MISTAKE 017 — clap wake should detect a transient, not just loudness
Date: 2026-04-18
What happened:
Even in clap-only standby, the live host run could still wake immediately from a loud non-clap block after calibration.
Result:
Passive standby violated the operator expectation that clap-only means actual clap-only wake.
Root cause:
The detector only looked at RMS loudness, so sustained loud blocks could masquerade as a clap candidate.
The fix:
Require a sharp transient shape with peak and crest-ratio checks before treating a block as the first clap.
Rule added:
Physical gesture detectors need branch tests for false positives, not just positive-detection checks.

HARD LESSON — routing fixes are not enough if timeout fallbacks are spoken as real answers
Date: 2026-04-11
What happened:
Even after fixing the question lane, Ollama timeouts still surfaced as `I'm still thinking, give me a moment.` and sounded like a valid answer.
Root cause:
The lightweight lane treated timeout fallback text from `brain/ollama_client.py` as a successful reply.
The fix:
The lightweight router now filters low-signal fallback replies and falls back to a clean generic question response instead of speaking fake progress text.

### MISTAKE 013 — Session closure docs were treated as optional instead of mandatory
Date: 2026-04-12
What happened:
Phase work was closed with tests and phase docs updated, but `.CODEX/Learning_loop.md` and the broader session-maintenance docs were not updated consistently at the same time.
Result:
Repo truth drifted between the master index, sprint history, and institutional memory files.
Root cause:
The session was anchored too narrowly on the short `AFTER EVERY SESSION` list in `.CODEX/Codex.md` and treated other required `.CODEX` maintenance files as optional.
The fix:
Expanded `.CODEX/Codex.md` so the mandatory closeout list explicitly includes:
`.CODEX/SPRINT_LOG.md`
`.CODEX/Learning_loop.md`
`.CODEX/Capability_Map.md` when capability truth changes
Rule added:
Session closure is not complete until `.CODEX/Codex.md`, `.CODEX/SPRINT_LOG.md`, `.CODEX/Learning_loop.md`, `docs/phases/PHASE_PROGRESS.md`, and `README.md` have each been checked and updated when applicable.
Verification:
Read `.CODEX/Codex.md` and confirm the mandatory closeout list explicitly names `.CODEX/SPRINT_LOG.md` and `.CODEX/Learning_loop.md`.

HARD LESSON — provider abstraction is fake if any helper keeps a direct Ollama POST path
Date: 2026-04-12
What happened:
The first Phase 3 pass touched `butler_config.py` and `brain/ollama_client.py`, but the classifier, smart-reply lane, startup briefing helper, and agent runner still had direct Ollama HTTP logic or hard-coded local model strings.
Root cause:
Provider work was scoped too narrowly to the main caller and ignored the smaller helper owners that had quietly grown their own model-routing logic.
The fix:
Moved those helpers back onto `brain/ollama_client.py`, replaced hard-coded model strings with config-backed role constants, and updated the speech layers to read provider target lists instead of fixed backend orders.
Rule added:
When introducing a provider abstraction, search the whole runtime for hard-coded models and raw transport calls before calling the abstraction complete.
Verification:
`venv/bin/pytest tests/test_ollama_client.py tests/test_agents.py tests/test_daemons.py tests/test_butler_pipeline.py tests/test_conversation_mode.py`

TEST INSIGHT — provider-aware tests should assert role selection, not stale literal local model names
Date: 2026-04-12
What happened:
Several focused regressions failed after the provider patch even though runtime behavior was correct, because the tests were asserting literal strings like `gemma4:e4b`.
Root cause:
The old tests encoded one specific local-model deployment instead of the higher-level contract: use the configured role model and fall back truthfully.
The fix:
Updated the regressions to assert config-backed role models, provider prefixes, or normalized fallback behavior rather than one old local-only model name.
Rule added:
When routing becomes config-driven, test the role contract and fallback semantics, not the previous concrete model string.
Verification:
`venv/bin/pytest tests/test_ollama_client.py tests/test_agents.py tests/test_daemons.py tests/test_butler_pipeline.py tests/test_conversation_mode.py`

HARD LESSON — summarization features are brittle if one optional extractor is treated as the capability
Date: 2026-04-12
What happened:
 Page summary was effectively blocked on Jina Reader and video summary was effectively blocked on `youtube_transcript_api`, even though the runtime already had enough surface area to try other text-acquisition paths.
Root cause:
 The feature was implemented as one happy-path dependency instead of a layered content-extraction chain with truthful fallbacks.
The fix:
 `executor/engine.py` now acquires page and video text through an ordered fallback chain:
 Jina -> direct HTML extraction for pages
 YouTube caption tracks -> `youtube_transcript_api` -> `yt-dlp` subtitles -> local Whisper -> Jina/page extraction for videos
Rule added:
 When a feature depends on external content acquisition, the capability owner must try multiple extraction paths before declaring the feature unavailable.
Verification:
 `venv/bin/pytest tests/test_executor.py tests/test_intent_router.py`

HARD LESSON — current-info features need a real public-data fallback, not just another model prompt
Date: 2026-04-12
What happened:
 `news` could route correctly but still degrade into a generic model summary whenever the live search backends came back thin or empty.
Root cause:
 The capability treated search acquisition as optional and let the model improvise once the fetch layer weakened.
The fix:
 `agents/runner.py` now keeps a real current-news fallback chain:
 SearXNG -> DuckDuckGo -> Exa -> Google News RSS
 and only narrates from what was actually fetched.
Rule added:
 For current-information features, add at least one public data fallback before letting the model answer from thin context.
Verification:
 `venv/bin/pytest tests/test_agents.py tests/test_pipeline_semantic_routing.py tests/test_butler_pipeline.py`

HARD LESSON — router params and executor enums need one normalized contract
Date: 2026-04-12
What happened:
 The new calendar-read tests exposed that the router was emitting `this_week` while the executor only recognized `this week`, so the feature silently fell back to the default range.
Root cause:
 The range contract was implicit and stringly-typed across two owners without a shared normalization rule.
The fix:
 `executor/engine.py` now normalizes calendar range tokens before dispatching the read logic, and the router regressions pin the exact phrases that map onto those ranges.
Rule added:
 When a route hands an enum-like string to another owner, normalize it at the boundary and add a regression for the exact transported value.
Verification:
 `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`

HARD LESSON — a master index is not enough if it hides the real repo root or omits mandatory docs
Date: 2026-04-12
What happened:
 A follow-up session picked the wrong working root and treated the phase files as the only mandatory reads, even though the active implementation lived under `mac-butler/` and the `.CODEX` rule files carried the real operating constraints.
Root cause:
 The session entry docs did not state the implementation root clearly enough and the required-reading list was narrower than the actual repo discipline.
The fix:
 `.CODEX/Codex.md` now pins `mac-butler/` as the implementation root, expands the required-reading list, and `docs/phases/PHASE.md` mirrors that same session-start order.
Rule added:
 If a repo has a wrapper workspace and a nested implementation root, the master index must name that root explicitly and list every mandatory session-start document in one place.
Verification:
 Read `.CODEX/Codex.md` and `docs/phases/PHASE.md` together and confirm they show the same implementation root and read order.

HARD LESSON — module-level helper imports across owner boundaries are brittle under package import order
Date: 2026-04-12
What happened:
 The browser slice validation exposed that `capabilities/registry.py` could silently lose `_gmail_compose_url` and `_youtube_search_url` when those helpers were imported eagerly at module load time.
Root cause:
 A cross-owner helper dependency was evaluated too early, so import order and partial module initialization could downgrade a real helper into `None`.
The fix:
 `capabilities/registry.py` now imports those router helpers lazily inside the action builders, so the typed action surface stays available once the router module is ready.
Rule added:
 When one core owner needs a helper from another owner, prefer a local lazy import at the use site over a module-level best-effort import that can fail silently.
Verification:
 `venv/bin/pytest tests/test_capabilities_planner.py`

HARD LESSON — a feature-completion phase needs bounded execution slices or the backlog stays fuzzy
Date: 2026-04-12
What happened:
 Phase 3 had real progress in browser, calendar, summarization, and news, but the phase docs still described it as one broad feature bucket, which made the next implementation target too easy to blur across unrelated domains.
Root cause:
 The roadmap tracked capability breadth, but not the execution order needed to land that breadth cleanly on the existing owners.
The fix:
 `docs/phases/PHASE.md` and `docs/phases/PHASE_PROGRESS.md` now break Phase 3 into explicit `3A` through `3D` slices:
 deterministic actions, retrieval quality, messaging/tooling, and HUD/proactive loops.
Rule added:
 When a phase spans multiple domains, split it into bounded slices that map to clear owners and a real build order before starting the next implementation patch.
Verification:
 Read `docs/phases/PHASE.md`, `docs/phases/PHASE_PROGRESS.md`, and `.CODEX/Capability_Map.md` together and confirm they describe the same slice order.

HARD LESSON — named filesystem locations need one normalized contract across router and executor
Date: 2026-04-12
What happened:
 The first filesystem regression pass still failed on natural phrases like `move resume to documents`, `copy resume to downloads`, and `open finder at downloads` even though the new CRUD routes existed.
Root cause:
 The parser only recognized location phrases with prepositions in some paths, while the executor and tests also used bare aliases like `documents` and `downloads`.
The fix:
 `intents/router.py` and `executor/engine.py` now normalize the same bare Desktop/Documents/Downloads/Home aliases, and the filesystem regressions pin those exact phrases.
Rule added:
 When a voice feature accepts named locations, normalize both bare aliases and preposition phrases at the routing boundary and again at the executor boundary.
Verification:
 `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`

HARD LESSON — action-shape tests need to cover both intent params and the final executor payload
Date: 2026-04-13
What happened:
 The first `3A` system-control pass exposed that `brightness` could carry a `level` from routing, but the final action boundary only preserved the old shape the executor expected for directional brightness changes.
Root cause:
 The slice had route tests and executor methods, but no regression pinned the transported action payload between those two owners.
The fix:
 `intents/router.py` now preserves both `direction` and `level` on `brightness` actions, `executor/engine.py` handles the absolute brightness path explicitly, and the regressions assert both the routed params and the final action payload.
Rule added:
 When a capability can travel in more than one payload shape, test the routed intent params and the post-`to_action()` payload together before trusting the executor behavior.
Verification:
 `venv/bin/pytest tests/test_intent_router.py tests/test_executor.py tests/test_butler_pipeline.py`

HARD LESSON — retrieval tests must isolate the live local knowledge-base state
Date: 2026-04-16
What happened:
 The first indexed-retrieval regressions accidentally read the real `memory/knowledge_base/index.json` in this worktree, so tests that were supposed to exercise the live-fetch branch short-circuited on cached page snapshots.
Root cause:
 The new retrieval layer is intentionally stateful, but the tests did not pin cache-hit versus cache-miss conditions explicitly.
The fix:
 The retrieval regressions now patch `memory.knowledge_base.get_indexed_document` to `None` for live-fetch branches and use explicit cached payloads only when the cache-hit behavior is the thing under test.
Rule added:
 Any test for cache-backed retrieval must set the cache state explicitly; never let the repo's real local index decide which branch a regression executes.
Verification:
 `venv/bin/pytest tests/test_agents.py tests/test_executor.py tests/test_remaining_items.py -q`

HARD LESSON — routing tests should pin capability intent, not an older fallback backend
Date: 2026-04-16
What happened:
 The first wider Phase 3B regression rerun failed even though the new weather path was correct, because the semantic-routing test still asserted that `lookup_weather` must call the old generic `search` agent.
Root cause:
 The regression had captured an implementation fallback instead of the capability contract. Once weather got its own dedicated provider path, the test became stale immediately.
The fix:
 `tests/test_pipeline_semantic_routing.py` now pins the `lookup_weather` capability and the dedicated `weather` agent action, while the generic-search branch stays covered separately in `tests/test_agents.py`.
Rule added:
 When a capability graduates from a generic fallback to a dedicated provider, update the route-level regression to assert the new owner and keep backend-fallback checks in the retrieval-owner tests.
Verification:
 `venv/bin/pytest tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py -q`

HARD LESSON — new feature tests should target the new branches, not just rerun legacy happy-path coverage
Date: 2026-04-16
What happened:
 The first retrieval patch had the right behavior, but the validation pass was still too shallow because most assertions were reusing older generic-search cases instead of pinning the new weather and direct-fact branches themselves.
Root cause:
 It is easy to mistake "the old suite still passes" for "the new behavior is well covered", especially when a feature moves from a fallback backend to a dedicated provider path.
The fix:
 The retrieval regressions now cover missing-input clarification, tomorrow-weather phrasing, DuckDuckGo infobox extraction, Wikipedia stripped-subject fallback, and the dedicated `weather` route explicitly.
Rule added:
 Every behavior change must add or tighten at least one test that directly exercises the new branch or failure mode; rerunning only legacy happy-path tests does not count as sufficient coverage.
Verification:
 `venv/bin/pytest tests/test_agents.py tests/test_capabilities_planner.py tests/test_pipeline_semantic_routing.py -q`

HARD LESSON — pending-dialogue memory should persist in the session-context owner, not leak into parallel state stores
Date: 2026-04-17
What happened:
 The runtime already persisted telemetry, project state, and long-term memory, but short-turn dialogue state in `brain/session_context.py` still vanished across a process restart because it only lived in RAM.
Root cause:
 Session-context ownership was treated like a purely transient helper even though the product relies on that owner for pending follow-ups and recent turns in the live hot path.
The fix:
 `brain/session_context.py` now writes a small persisted snapshot for recent turns and pending state, restores it on fresh startup when it is recent enough, and the new regressions pin both the restore and stale-snapshot skip branches.
Rule added:
 If an owner is the live source of truth for hot-path dialogue state, persistence belongs in that owner or its explicit storage boundary, not in an unrelated telemetry or long-term memory file.

HARD LESSON — background smoke automation must use the same safe entrypoints the docs advertise
Date: 2026-04-17
What happened:
 The background bug hunter was still shelling the broad default `system_check.py --json` path even though the live docs and phase tracker only advertised the safe phase-scoped host smoke surfaces.
Root cause:
 The daemon predates the newer phase-scoped smoke contract and never got reconciled after the safer host harness split landed.
The fix:
 `daemon/bug_hunter.py` now runs the documented `--phase1-host --phase1-host-only` and `--phase3a-host --phase3a-host-only` checks together, and the daemon regression now pins those exact arguments.
Rule added:
 Any background verifier or watchdog must call the same scoped smoke entrypoints the docs and operators rely on; never let a daemon silently widen the blast radius.

HARD LESSON — latency work needs branch tests for both the skip path and the fetch path
Date: 2026-04-18
What happened:
 The retrieval latency slice only becomes trustworthy if the code proves both that rich provider snippets skip the expensive live page fetch and that thin snippets still trigger the fetch when needed.
Root cause:
 Performance changes are easy to validate only on the “faster” branch and accidentally miss the thin-content fallback that keeps answer quality intact.
The fix:
 The new retrieval regressions now pin repeated-query cache reuse, rich-snippet skip behavior, thin-snippet fetch behavior, and the top-result semantic fetch skip branch directly in `tests/test_agents.py`.
Rule added:
 Any latency optimization that skips work conditionally must add at least one regression for the fast path and one for the quality-preserving fallback path.

HARD LESSON — timeout filler is not a user answer
Date: 2026-04-19
What happened:
 A live `latest news` run routed to NVIDIA first, then to the Ollama fallback after the NVIDIA call failed or timed out, and the fallback timeout text `I'm still thinking, give me a moment.` was spoken as if it were a real news answer.
Root cause:
 The current-news agent validated empty and raw-artifact responses, but it did not classify low-signal model timeout filler as invalid model output.
The fix:
 `agents/runner.py` now rejects low-signal timeout filler in news summaries and returns collected headlines/snippets or a truthful fetch failure instead; new tests pin both the collected-items branch and the empty-live-fetch branch.
Rule added:
 Provider timeout/progress text must never cross from an internal model fallback into speech as a completed answer; every current-info route needs a regression for that failure mode.

HARD LESSON — localhost dashboard and native HUD must not auto-open together
Date: 2026-04-19
What happened:
 The runtime could serve localhost and auto-open the native pywebview HUD in the same launch, creating confusing split surfaces during live debugging.
Root cause:
 Native HUD launch was the default instead of an explicit operator opt-in.
The fix:
 `projects/dashboard.py` now defaults to localhost `7532/7533`, keeps native pywebview HUD and browser auto-open opt-in only, and the new dashboard regression proves no window opens without opt-in.
Rule added:
 A live runtime should have one operator surface by default; any parallel surface must be explicitly enabled and documented.

HARD LESSON — a fallback chain is fake if timeout exits early
Date: 2026-04-19
What happened:
 The model config advertised fallback candidates, but a timed-out NVIDIA model returned `I'm still thinking, give me a moment.` immediately instead of trying the next configured model.
Root cause:
 Timeout handling was different from other provider failures and short-circuited the retry loop.
The fix:
 `brain/ollama_client.py` now treats timeout as a retryable candidate failure, uses the live-passing NVIDIA Gemma E4B path for hot output, keeps NVIDIA Gemma 4 31B in deeper fallback chains, strips Gemma thought/channel wrappers, and only returns empty after the whole chain is exhausted.
Rule added:
 Provider fallback chains must have tests for timeout continuation and provider-specific output cleanup, not just non-timeout exceptions.

HARD LESSON — speech I/O models are not the text-output brain
Date: 2026-04-19
What happened:
 The NVIDIA Parakeet `1.1B` ASR model was mistaken for the model producing Butler's spoken answers.
Root cause:
 The docs grouped LLM, TTS, and STT providers too tightly and did not state that ASR is only for listening/transcription.
The fix:
 Docs now separate output/conversation models from TTS and STT, with NVIDIA Gemma E4B leading hot text output after live validation and Parakeet kept only as the listening model.
Rule added:
 Model docs must separate text generation, text-to-speech, and speech-to-text roles because their model sizes and quality tradeoffs are not interchangeable.

HARD LESSON — tool-required questions must not ask the lightweight model first
Date: 2026-04-19
What happened:
 A live current-role question like `who is PM of India` could be answered by lightweight/model fallback or drift into news-style material instead of using the retrieval path.
Root cause:
 The question branch computed tool preference too late; it asked the lightweight model before enforcing retrieval for current-role facts. The semantic planner also missed the `PM` abbreviation.
The fix:
 Current-role questions now match deterministic role patterns, skip lightweight narration, and execute `lookup_web` through the search agent. New tests pin the planner branch and the full `handle_input` route so it cannot regress into news or model-only output.
Rule added:
 Any question class that requires current data must establish tool preference before any model-only answer path runs, including abbreviation variants.

HARD LESSON — old skills can steal verified owner paths
Date: 2026-04-19
What happened:
 Calendar-create phrasing could be caught by the legacy calendar skill before the deterministic router/executor path, causing bad clarification or read-style behavior.
Root cause:
 The skill still advertised calendar creation even though verified calendar writes now belong to `intents/router.py` and `executor/engine.py`.
The fix:
 `skills/calendar_skill.py` is now read-only, inline calendar-create parsing is deterministic, and new regressions pin both `add meeting tomorrow 3pm` routing and the skill no-steal branch.
Rule added:
 When a verified owner path exists, older skills must either delegate to that owner or stop matching the write/action phrase.

HARD LESSON — Obsidian iCloud paths need vault-relative open URLs
Date: 2026-04-19
What happened:
 Obsidian showed `Unable to find a vault` for a note URL like `obsidian://open?path=/Users/.../iCloud~md~obsidian/Documents/Burry/Daily/2026-04-19 2026-04-19.md`.
Root cause:
 Butler opened notes with a raw absolute iCloud path and also prepended the daily date even when the title was already the date.
The fix:
 `executor/engine.py` now opens notes with `obsidian://open?vault=Burry&file=Daily/...` whenever the note is inside the configured vault and uses `Daily/YYYY-MM-DD.md` instead of duplicating date titles.
Rule added:
 Obsidian memory links should be vault-relative when the vault name is known; absolute iCloud paths are only a fallback.

HARD LESSON — deterministic routes must not wait behind classifier timeouts
Date: 2026-04-19
What happened:
 A live PM question returned the right answer only after waiting on timed-out classifier models, and inline calendar create phrases had the same risk.
Root cause:
 `route()` called the configured classifier before accepting high-confidence deterministic matches from the legacy router.
The fix:
 `intents/router.py` now accepts high-confidence deterministic matches before classifier fallback, and new regressions assert PM questions plus inline calendar creates do not call the classifier.
Rule added:
 The classifier is a fallback for deterministic misses, not a prerequisite for known high-confidence local routes.

HARD LESSON — required docs need executable contract checks
Date: 2026-04-19
What happened:
 `.CODEX/AGENTS.md`, `.CODEX/ARCHITECTURE.md`, and `docs/phases/PHASE_PROGRESS.md` described deterministic-router-before-classifier correctly, but `.CODEX/Codex.md` and `docs/phases/PHASE.md` still had an older skills-to-classifier flow.
Root cause:
 The routing behavior had code and router regressions, but no test read the required docs as part of the contract.
The fix:
 `.CODEX/Codex.md` and `docs/phases/PHASE.md` now pin `pending -> instant -> skills -> deterministic router -> classifier`, and `tests/test_docs_runtime_contract.py` fails if required docs drift from that order again.
Rule added:
 Any mandatory operating contract in required docs should have at least one executable consistency check when drift has already caused confusion.

HARD LESSON — dashboard status probes must use the same health contract as backend probes
Date: 2026-04-19
What happened:
 Backend SearXNG readiness had moved to the JSON `/search` probe, but dashboard operator status still checked the SearXNG root page.
Root cause:
 The dashboard status probe was separate from the backend health path and did not get a matching regression.
The fix:
 `projects/dashboard.py` now builds a JSON SearXNG health URL with `/search?q=butler-health&format=json`, and `tests/test_dashboard.py` pins that exact probe.
Rule added:
 Shared provider readiness semantics must be tested at every owner that reports them; a healthy HTML root page is not the same as a working JSON search backend.

HARD LESSON — benchmark success must reject fallback-shaped answers
Date: 2026-04-19
What happened:
 The first real-task benchmark run marked PM quick-fact and weather probes as `ok` even though they returned unavailable fallback text inside the sandbox.
Root cause:
 The benchmark measured latency and agent status but did not require the expected retrieval tool or reject fallback-shaped answers like `I couldn't look that up right now`.
The fix:
 `scripts/benchmark_models.py --real-tasks` now fails retrieval cases when output is low-signal filler, unavailable fallback text, or the expected tool is missing or wrong. New tests pin all three branches.
Rule added:
 A benchmark is not just a timer; it must validate answer quality and the expected tool path before a fast result counts as a win.
