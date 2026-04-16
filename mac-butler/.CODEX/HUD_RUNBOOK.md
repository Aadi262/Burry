HUD Runbook — how to run, stop, debug the dashboard
Start everything
Step 1 — SearXNG (required for news)
cd ~/Burry/mac-butler
bash scripts/start_searxng.sh
Step 2 — HUD server (Terminal 1)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler 
venv/bin/python projects/dashboard.py
Step 3 — Voice pipeline (Terminal 2)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler 
venv/bin/python butler.py
Step 4 — Open HUD
open http://127.0.0.1:3333
Stop everything
pkill -f "butler.py"
pkill -f "dashboard.py"
pkill -f "trigger.py"
pkill -f "python"
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
HUD HTTP:  localhost:3333
HUD WS:    localhost:3334/ws
SearXNG:   localhost:8080
Ollama:    localhost:11434 or 127.0.0.1:11434
Common issues
"Something went wrong" on butler --test
→ Ollama not running: ollama serve
HUD shows offline
→ dashboard.py not running
News times out
→ SearXNG not running: bash scripts/start_searxng.sh
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