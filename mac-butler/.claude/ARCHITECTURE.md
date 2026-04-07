# Burry OS Architecture Map

## Voice Pipeline (critical path — must stay fast)
clap → trigger.py
→ STT (whisper/mlx)
→ handle_input(text) in butler.py
→ skills.match_skill() — check skills first
→ intents.router.route() — intent routing
→ fast path: greeting/question → _call() direct
→ slow path: tool intents → run_agentscope_turn()
→ AgentScopeBackbone.run_turn()
→ _ensure_model() — cached agent lookup
→ agent(Msg) — ReAct loop
→ hooks fire (WS broadcast only)
→ tool calls via Toolkit
→ streaming tokens via msg_queue
→ on_sentence() → speak() → TTS
→ record_episode_with_agentscope_feedback()
→ save state

## Memory System (3 tiers)
Working memory:  last 6 turns in InMemoryMemory (lost on restart)
Recent memory:   last 7 days in memory/long_term_memory.json
Archive memory:  compressed summaries in long_term_memory.json
Session persist: memory/burry_session.json (save on SIGTERM)
Semantic search: nomic-embed-text via memory/store.py
Knowledge base:  memory/knowledge_base/ (custom + AgentScope RAG)

## AgentScope Backbone (brain/agentscope_backbone.py)
Key caches (module-level, persist for process lifetime):
_INTENT_TOOLKIT_CACHE  — toolkit per intent key
_AGENT_CACHE           — ReActAgent per (intent, model)
_MCP_TOOLS_CACHE       — MCP tools scanned once at startup
_PERSISTENT_LOOP       — single asyncio loop, never recreated
Intent → num_ctx mapping (keep these small for speed):
greeting/music/volume  → 1024
open_project/email     → 2048
question/what_next     → 4096
plan/research          → 8192
Hooks (WS broadcast ONLY — no LLM calls):
pre_reply    → broadcast agent_thinking
post_reply   → broadcast agent_reply + write memory
pre_acting   → broadcast tool_start
post_acting  → broadcast tool_end
pre_reasoning → broadcast agent_thinking

## Frontend (projects/frontend/)
app.js          — entry point, imports all modules
modules/
orb.js        — Three.js neural orb (5 states)
graph.js      — project dependency graph canvas
stream.js     — WebSocket handler + ALL WS event types
panels.js     — left/right rail panel rendering + TOOL_MAP
events.js     — events feed (right rail)
commands.js   — command dock input + send
mac-activity.js — mac activity panel
WS message types handled in stream.js:
operator, projects, tool_start, tool_end,
agent_thinking, agent_reply, agent_chunk,
plan_update

## Models (butler_config.py)
voice:     gemma4:e4b  (9.6GB)
planning:  gemma4:e4b
reasoning: deepseek-r1:14b
agents:    gemma4:e4b
embedding: nomic-embed-text (274MB)
fallback:  gemma4:26b  (17GB — only if RAM > 12GB free)
