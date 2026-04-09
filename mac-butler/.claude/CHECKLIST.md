Pre-commit Checklist — run before EVERY commit
1. Timing test (MANDATORY)
time PYTHONPATH=/Users/adityatiwari/Burry/mac-butler 
venv/bin/python butler.py --command 'hi how are you' 2>&1 | tail -3
PASS: under 8 seconds
FAIL: investigate hooks and ws_broadcast first
2. Full test suite (MANDATORY)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler 
venv/bin/python -m unittest discover -s tests -q 2>&1 | tail -3
PASS: 0 failures
3. Import health (MANDATORY)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
import brain.agentscope_backbone
import brain.toolkit
import agents.runner
import memory.long_term
import channels.a2a_server
print('All imports OK')
" 2>&1 | grep -v WARNING | grep -v LiteLLM
4. JS syntax check (if frontend changed)
node --check projects/frontend/modules/stream.js 
projects/frontend/modules/panels.js 
projects/frontend/modules/events.js 
projects/frontend/modules/commands.js
echo "JS OK"
5. Hook safety check (if backbone changed)
grep -n "get_compressed_context|_call(|ollama|LLM" 
brain/agentscope_backbone.py | grep -i "hook|pre_reply|post_reply"
PASS: nothing found
FAIL: you put an LLM call inside a hook — remove it
6. Never commit these files
memory/runtime_state.json
memory/mood_state.json
memory/burry_session.json
memory/rl_experience.json
memory/long_term_memory.json
memory/layers/graph.json
tasks/tasks.json (runtime data)
memory/knowledge_base/
7. Real smoke tests (run manually after every session)
Test 1: natural language news
Say "yo what is happening in india today bro"
PASS: India news spoken
FAIL: "I didn't catch that" or "Say open, search..." = routing broken
Test 2: YouTube vs Spotify
Say "play blinding lights on youtube"
PASS: YouTube opens
FAIL: Spotify opens = platform detection broken
Test 3: folder path
Say "create folder called client work on desktop"
PASS: ~/Desktop/client work created
FAIL: folder named "client work on desktop" = path parsing broken
Test 4: terminal single instance
Say "open terminal" twice
PASS: one terminal window
FAIL: two windows = no instance check
Test 5: multi-turn email
Say "write mail to vedang" → answer subject → answer body
PASS: Gmail fills both fields
FAIL: Gmail opens empty = session_context broken
Test 6: tasks
Say "what are my tasks today"
PASS: real tasks spoken
FAIL: unknown intent = routing broken
Test 7: battery
Say "how much battery do i have"
PASS: real percentage spoken
FAIL: unknown = LLM classifier not wired
Test 8: news with topic
Say "latest news on claude mythos"
PASS: news spoken in under 15 seconds
FAIL: timeout or silence = SearXNG offline or classifier broken
Test 9: conversation
Say "lets brainstorm adpilot architecture"
PASS: Burry talks back with opinions naturally
FAIL: "I didn't understand" = conversation mode broken
Test 10: summarize page
Say "summarize this page"
PASS: current Chrome page summarized and spoken
FAIL: unknown = Jina Reader not wired