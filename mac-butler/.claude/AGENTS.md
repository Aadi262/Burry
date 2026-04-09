Burry OS — Codex Agent Rules
READ THIS BEFORE TOUCHING ANYTHING
Architecture

butler.py — main voice pipeline, 3000+ lines
brain/agentscope_backbone.py — AgentScope orchestrator
brain/ollama_client.py — LLM calls, SYNC, has rate limiter
brain/session_context.py — session memory across turns
brain/mood_engine.py — personality and mood
brain/briefing.py — startup briefing
agents/runner.py — specialist fan-out via MsgHub
intents/router.py — PRIMARY router (gemma4:e4b classifier)
pipeline/router.py — wrapper: cache + lane selection only
pipeline/orchestrator.py — AgentScope path
pipeline/recorder.py — memory writes (async via bus only)
memory/store.py — JSONL sessions + semantic search
memory/long_term.py — 3-tier memory (working/recent/archive)
memory/bus.py — ONLY memory write path on hot path
executor/engine.py — action dispatcher (50+ actions)
projects/dashboard.py — HUD WebSocket server
projects/frontend/ — HUD (ES modules, Three.js orb)
skills/ — email, calendar, imessage skills

THE CORE ARCHITECTURAL DECISION
Burry is NOT a command center.
Burry is a natural language agent.
The routing flow (strict order, never skip):

trigger.py → session_context.reset()
STT → transcribed text
session_context.has_pending() → resolve pending FIRST
Check 12 instant patterns (no LLM, under 1ms)
skills matcher → email/calendar/imessage
gemma4:e4b classifier → intent + params JSON
If confidence > 0.7 → executor/engine.py directly
If confidence 0.4-0.7 → ask one clarifying question
If confidence < 0.4 → conversation mode
session_context.add_butler() → remember response
memory/bus.py → async write ONLY (never sync on hot path)
speak response

GOLDEN RULES — never violate these

NEVER call LLM inside a hook
Hooks fire before/after every LLM call
Calling LLM inside hook = infinite loop or 2x latency
Hooks are for: WS broadcast, logging, state updates ONLY
NEVER use asyncio.run() inside an AgentScope tool
AgentScope tools run inside an async event loop
asyncio.run() inside running loop = RuntimeError crash
Fix: use concurrent.futures.ThreadPoolExecutor instead
NEVER make _ws_broadcast() blocking
It must always fire in a background thread
Blocking ws_broadcast = every LLM call waits for WS
NEVER call agentscope.init() more than once
It is a global singleton
Multiple calls = race conditions on init name
Only backbone.py calls it via ensure_agentscope_initialized()
ALWAYS use session_context for turn memory
Never pass state through global variables
ctx.has_pending() BEFORE routing every single time
NEVER write to more than 1 memory system per command
All writes go through memory/bus.py only
No sync writes in the hot path ever
NEVER add a feature without wiring it end to end
Dead code makes the architecture worse not better
If you build it, connect it, test it, commit it
NEVER leave a file that imports nowhere
After every session grep for unused files
Delete them or integrate them
NEVER use deepseek-r1:14b on the voice hot path
It is slow (9GB). Use gemma4:e4b for all real-time work
deepseek-r1:14b only for background search/research
NEVER block the voice pipeline with a slow operation
Slow ops go in background threads
The voice pipeline must always return in under 8s

Current timing baseline

Greeting:       under 5 seconds
Simple command: under 3 seconds
News/search:    under 15 seconds (with SearXNG)
Email compose:  under 5 seconds
Conversation:   under 6 seconds
Research:       under 60 seconds (background only)

Test baseline

Run: PYTHONPATH=. venv/bin/python -m unittest discover -s tests -q
Must be: 0 failures

AgentScope version gaps (as of Apr 2026)

agentscope.agents — NOT available (no BrowserAgent/DeepResearchAgent)
agentscope.server — NOT available (no AgentService)
agentscope.tuner — record_feedback NOT available
agentscope.rag.KnowledgeBank — NOT available (use SimpleKnowledge)
All have fallbacks — do not try to force these imports

Models installed (as of Apr 2026)
gemma4:26b       17GB  — planning, VPS only, never local hot path
gemma4:e4b       9.6GB — classifier, voice, conversation, agents, DEFAULT
deepseek-r1:14b  9.0GB — search, news, research ONLY (slow)
nomic-embed-text 274MB — embeddings only
DO NOT reference models not in this list.
DO NOT add model chains longer than 3 models.
Commit discipline

Commit each logical unit separately
Never commit memory/*.json or tasks/ or runtime_state.json
Always run tests before commit
Always run timing test after touching backbone/hooks

HOW TO START BURRY (exact commands)
Terminal 1 — HUD
cd ~/Burry/mac-butler
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python projects/dashboard.py
Terminal 2 — Voice pipeline
cd ~/Burry/mac-butler
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python butler.py
Open HUD
open http://127.0.0.1:3333
Start SearXNG (required for news/search)
bash scripts/start_searxng.sh
HOW TO STOP BURRY
pkill -f "butler.py"
pkill -f "dashboard.py"
pkill -f "trigger.py"
NEVER DO THESE AT STARTUP

Never run trigger.py --both unless asked
Never start Burry without checking RAM first
Never close browser tab and assume Burry stopped
top -l 1 | grep PhysMem must show >4GB free before starting