HUD Runbook — how to run, stop, debug the dashboard
Start everything
Step 1 — SearXNG (required for news)
cd ~/Burry/mac-butler
bash scripts/start_searxng.sh
Step 2 — HUD server (Terminal 1)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler 
venv/bin/python projects/dashboard.py
Default localhost endpoint:
http://127.0.0.1:7532
Override the HUD port only when needed:
BURRY_HUD_PORT=7642 BURRY_HUD_WS_PORT=7643 PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python projects/dashboard.py
Native pywebview HUD is off by default. Use `BURRY_USE_NATIVE_HUD=1` only when explicitly testing the native shell.
Step 3 — Butler backend / passive standby (Terminal 2)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler 
venv/bin/python butler.py
This keeps the backend live on `3335`, but it no longer auto-speaks or auto-enters STT.
Voice wakes only after clap, the optional wake phrase path, or an explicit HUD/API command.
For clap-only local runs:
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python butler.py --clap-only
Step 4 — Open HUD
open http://127.0.0.1:7532
Do not open localhost and native HUD together. Browser auto-open is opt-in with `BURRY_ALLOW_BROWSER_HUD=1`.
Stop everything
pkill -f "butler.py|projects/dashboard.py|trigger.py|projects/native_shell.py|channels/a2a_server.py|agents/runner.py"
sleep 2
sudo purge
top -l 1 | grep PhysMem  # must show >4GB free
WS event types (stream.js handles all of these)
operator            — session state update
projects            — project list update
tool_start          — tool execution starting
tool_end            — tool execution complete
agent_thinking      — model reasoning
agent_reply         — model response chunk
agent_chunk         — streaming token
plan_update         — plan step update
pending_update      — session context pending state
mood_update         — mood state change
memory_read         — memory being queried
classifier_result   — intent classification result
briefing_spoken     — startup briefing text
Ports
HUD HTTP:  localhost:7532
HUD WS:    localhost:7533/ws
Backend:   localhost:3335/api/v1/health
SearXNG:   localhost:8080
Ollama:    localhost:11434 or 127.0.0.1:11434
Common issues
"Something went wrong" on butler --test
→ Ollama not running: ollama serve
HUD shows offline
→ dashboard.py not running
Second Butler backend refuses to start
→ another long-lived `butler.py` already owns the live runtime lock
→ reuse the existing backend on `3335` or stop it before starting another
News times out
→ SearXNG not running: bash scripts/start_searxng.sh
→ Provider/model timeout text must not be spoken as the answer; the news agent should fall back to collected headlines/snippets or a truthful fetch failure.
70 second responses
→ LLM call inside a hook: check agentscope_backbone.py
→ Run: grep -n "_call|get_compressed" brain/agentscope_backbone.py | grep hook
Two terminals open
→ open_app not checking if Terminal already running
→ Fix: add osascript check in executor/engine.py open_app
"I didn't catch that" for everything
→ gemma4:e4b classifier not wired
→ Check: intents/router.py — does it call gemma4:e4b?
RAM full
→ sudo purge
→ ollama ps (check what models are loaded)
→ ollama stop gemma4:26b (unload big model)
