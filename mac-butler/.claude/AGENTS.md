# Burry OS — Codex Agent Rules

## READ THIS BEFORE TOUCHING ANYTHING

### Architecture
- butler.py — main voice pipeline, 3000+ lines
- brain/agentscope_backbone.py — AgentScope orchestrator
- brain/ollama_client.py — LLM calls, SYNC, has rate limiter
- agents/runner.py — specialist fan-out via MsgHub
- intents/router.py — intent matching
- memory/store.py — JSONL sessions + semantic search
- memory/long_term.py — 3-tier memory (working/recent/archive)
- projects/dashboard.py — HUD WebSocket server
- projects/frontend/ — HUD (ES modules, Three.js orb)

### GOLDEN RULES — never violate these

1. NEVER call LLM inside a hook
   Hooks fire before/after every LLM call
   Calling LLM inside hook = infinite loop or 2x latency
   Hooks are for: WS broadcast, logging, state updates ONLY

2. NEVER use asyncio.run() inside an AgentScope tool
   AgentScope tools run inside an async event loop
   asyncio.run() inside running loop = RuntimeError crash
   Fix: use concurrent.futures.ThreadPoolExecutor instead

3. NEVER make _ws_broadcast() blocking
   It must always fire in a background thread
   Blocking ws_broadcast = every LLM call waits for WS

4. NEVER call agentscope.init() more than once
   It is a global singleton
   Multiple calls = race conditions on init name
   Only backbone.py calls it via ensure_agentscope_initialized()

5. ALWAYS wrap new LLM calls with rate limiter
   from brain.rate_limiter import get_limiter
   with get_limiter(): ... your call ...

6. ALWAYS test timing after touching backbone or hooks
   Target: under 8 seconds for greeting
   time venv/bin/python butler.py --command 'hi' 2>&1 | tail -3

7. NEVER remove the fast path for simple intents
   greeting/question/chitchat skip AgentScope ReAct loop
   They call _call() directly — this is intentional

### Current timing baseline
- Greeting: 7.9s target (was 61.9s when hooks blocked)
- Tool calls: 15-30s acceptable
- Deep research: 60-90s acceptable

### Test baseline
- 396 tests, 0 failures
- Run: PYTHONPATH=. venv/bin/python -m unittest discover -s tests -q

### AgentScope version gaps (as of Apr 2026)
- agentscope.agents — NOT available (no BrowserAgent/DeepResearchAgent)
- agentscope.server — NOT available (no AgentService)
- agentscope.tuner — record_feedback NOT available
- agentscope.rag.KnowledgeBank — NOT available (use SimpleKnowledge)
- All have fallbacks — do not try to force these imports

### Known pre-existing issues (do not spend time on these)
- SearXNG offline — not installed, fallback to browser agent works
- AppleScript syntax error in iMessage test — pre-existing macOS quirk
- GitHub MCP not ready — GITHUB_PERSONAL_ACCESS_TOKEN not set
- agentscope.server A2A — custom server is the fallback, works fine

### Commit discipline
- Commit each logical unit separately
- Never commit memory/*.json or tasks/ or runtime_state.json
- Always run tests before commit
- Always run timing test after touching backbone/hooks
