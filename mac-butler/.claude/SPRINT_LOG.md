# Sprint Log — what was done, what broke, what was learned

## Sprint: AgentScope Integration (Apr 2026)
Commits: 5c97615 → 4211471

### Done
- AgentScope Toolkit replacing 200-line if/elif
- MsgHub fanout in agents/runner.py
- Streaming TTS via stream_printing_messages
- Skills auto-loader (skills/ directory)
- Memory compression (get_compressed_context)
- QPM rate limiter (brain/rate_limiter.py)
- OTel tracing (runtime/tracing.py)
- iMessage channel (channels/imessage_channel.py)
- async httpx client for daemons
- Pydantic structured output (brain/structured_output.py)
- MCP tool cache at startup
- Persistent event loop (no per-turn asyncio.run)
- Intent-scaled num_ctx (greeting=1024, research=8192)
- Single agentscope.init (ensure_agentscope_initialized)
- All 5 lifecycle hooks registered
- Frontend WS handlers for all AgentScope events
- Full TOOL_MAP (15+ tools with icons)
- New HUD panels (agent-trace, tool-exec, plan-steps)
- PlanNotebook → WS plan_update events
- OTel tracing URL auto-detect (Phoenix at :4318)
- AgentScope RAG with SimpleKnowledge + MilvusLite
- Session persistence (save_session_state on SIGTERM)
- RL episode wrapper (record_episode_with_agentscope_feedback)
- A2A server with AgentScope native fallback

### Broken and fixed
- _compression_config returned None → moved dead code into function
- call_server_tool wrong arg order → fixed to keyword args
- asyncio.run() in planner/research → thread pool dispatch
- double agentscope.init() → consolidated to ensure_agentscope_initialized
- intent_name not threaded → added to run_agentscope_turn signature
- TIMING REGRESSION 7.9s→61.9s → pre_reply_hook was calling LLM
  Fix: hooks must ONLY do WS broadcast, never call LLM
  Fix: _ws_broadcast must be non-blocking (background thread)

### Package gaps (Apr 2026)
- agentscope.agents → no BrowserAgent/DeepResearchAgent
- agentscope.server → no AgentService
- agentscope.tuner → no record_feedback
- agentscope.rag → no KnowledgeBank (use SimpleKnowledge)
- All have fallbacks wired

### Remaining (next sprint)
- Fix timing regression (hooks blocking LLM)
- agentscope.agents when package updated
- agentscope.server when agentscope-runtime installs
- SearXNG local instance for web search
- Email multi-turn flow still fragile
