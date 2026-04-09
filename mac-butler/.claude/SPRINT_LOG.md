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
