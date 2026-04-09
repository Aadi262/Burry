Burry OS Architecture Map
Voice Pipeline (critical path — must stay fast)
clap/keyboard → trigger.py
  → session_context.reset()
  → brain/briefing.py build_briefing() → speak briefing
  → STT (mlx-whisper)
  → handle_input(text, ctx) in butler.py
      → ctx.has_pending()? → _resolve_pending(text, ctx)
      → instant pattern check (12 patterns, no LLM)
      → skills.match_skill(text) → use skill if match
      → gemma4:e4b classify intent → JSON {intent, params, confidence}
      → if confidence > 0.7 → executor/engine.py
      → if confidence 0.4-0.7 → ask clarifying question
      → if confidence < 0.4 → conversation mode (gemma4:e4b)
      → ctx.add_butler(response)
      → memory/bus.py record() [async, non-blocking]
      → speak(response)
Intent Classifier (gemma4:e4b — the brain)
Input:  text + last 4 turns from session_context
Output: {intent, params, confidence, platform, needs_confirmation}

Available intents (35 total):
news, play_music, open_app, compose_email,
create_folder, create_file, read_file, write_file,
delete_file, find_file, list_files, move_file,
open_url, browser_tab, browser_window, web_search,
volume_control, brightness, compose_whatsapp,
calendar_read, calendar_add, task_read, task_add,
task_done, obsidian_note, run_command, open_project,
git_action, vps_check, summarize_page, summarize_video,
read_screen, take_screenshot, focus_app, quit_app,
minimize_app, system_info, dark_mode, do_not_disturb,
conversation, unknown
Session Memory (brain/session_context.py)
SessionContext:
  turns: list of {role, text, intent, action, timestamp}
  pending: {type, collected, missing}
  topic: current conversation topic

Key methods:
  add_user(text, intent, action)
  add_butler(text)
  recent_history(n=4) → string of last N turns
  has_pending() → bool
  set_pending(type, collected, missing)
  clear_pending()
  reset() → called on every new session
  get_context() → global singleton
Memory System (simplified — one write path)
Hot path (every command):
  memory/bus.py record() → batched append to event_log.jsonl
  (async, non-blocking, flushes every 2 seconds)

Background (every 60 seconds):
  memory/long_term.py → compress to working/recent/archive
  memory/store.py → update butler_memory.json

Read path (into LLM prompts):
  brain/ollama_client.py _get_memory() →
    memory/store.py get_last_session_summary()
    memory/layered.py get_memory_index()
AgentScope Backbone (brain/agentscope_backbone.py)
Key caches (module-level):
  _INTENT_TOOLKIT_CACHE  — toolkit per intent key
  _AGENT_CACHE           — ReActAgent per (intent, model)
  _MCP_TOOLS_CACHE       — MCP tools scanned once at startup
  _PERSISTENT_LOOP       — single asyncio loop, never recreated

Hooks (WS broadcast ONLY — NO LLM calls ever):
  pre_reply    → broadcast agent_thinking
  post_reply   → broadcast agent_reply
  pre_acting   → broadcast tool_start
  post_acting  → broadcast tool_end
  pre_reasoning → broadcast agent_thinking
Executor Actions (executor/engine.py)
System:   volume_up, volume_down, volume_set, brightness_up,
          brightness_down, lock_screen, sleep_mac, show_desktop,
          dark_mode, do_not_disturb, system_info, screenshot

Browser:  browser_new_tab, browser_close_tab, browser_new_window,
          browser_go_back, browser_refresh, browser_go_to,
          open_url (with URL_MAP for google docs, sheets, etc)

Files:    create_file, read_file, write_file, delete_file,
          find_file, list_files, move_file, create_folder

Apps:     open_app (with single-instance check), focus_app,
          quit_app, minimize_app, open_project (with editor chain)

Media:    spotify_search_play, spotify_pause, spotify_next,
          spotify_prev, spotify_volume, play_on_youtube

Email:    compose_email (with PyAutoGUI fill), send_email

Comms:    compose_whatsapp, whatsapp_open

Calendar: calendar_read (osascript), calendar_add (osascript)

Tasks:    task_read, task_add, task_done

Notes:    obsidian_note

Terminal: run_command, open_terminal, open_project

VPS:      vps_check, ssh_command

AI:       summarize_page (Jina Reader + gemma4:e4b)
          summarize_video (yt-transcript-api + gemma4:e4b)
          read_screen (screenshot + vision/OCR)
Frontend (projects/frontend/)
app.js          — entry point, imports all modules
modules/
  orb.js        — Three.js neural orb (5 states)
  graph.js      — project dependency graph canvas
  stream.js     — WebSocket handler + ALL WS event types
  panels.js     — left/right rail panel rendering + TOOL_MAP
  events.js     — events feed (keep last 100 events)
  commands.js   — command dock input + send
  mac-activity.js — mac activity panel

WS message types handled in stream.js:
  operator, projects, tool_start, tool_end,
  agent_thinking, agent_reply, agent_chunk,
  plan_update, pending_update, mood_update,
  memory_read, classifier_result, briefing_spoken
Models (butler_config.py)
classifier/voice/conversation: gemma4:e4b (9.6GB) — DEFAULT
search/news/research:          deepseek-r1:14b (9.0GB) — SLOW, background
embeddings:                    nomic-embed-text (274MB)
vps/planning:                  gemma4:26b (17GB) — VPS ONLY
Editor Fallback Chain (open_project)
pythonEDITOR_CHAIN = [
    ("claude", lambda p: ["claude", p]),
    ("codex",  lambda p: ["codex", p]),
    ("cursor", lambda p: ["cursor", p]),
    ("code",   lambda p: ["code", p]),
]
# Try each. Use first one found in PATH.