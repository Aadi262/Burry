# Pre-commit Checklist — run before EVERY commit

## 1. Timing test (MANDATORY)
time PYTHONPATH=/Users/adityatiwari/Burry/mac-butler \
  venv/bin/python butler.py --command 'hi how are you' 2>&1 | tail -3
# PASS: under 10 seconds
# FAIL: investigate hooks and ws_broadcast first

## 2. Full test suite (MANDATORY)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler \
  venv/bin/python -m unittest discover -s tests -q 2>&1 | tail -3
# PASS: 396+ tests, 0 failures

## 3. Import health (MANDATORY)
PYTHONPATH=/Users/adityatiwari/Burry/mac-butler venv/bin/python -c "
import brain.agentscope_backbone
import brain.toolkit
import agents.runner
import memory.long_term
import channels.a2a_server
print('All imports OK')
" 2>&1 | grep -v WARNING | grep -v LiteLLM

## 4. JS syntax check (if frontend changed)
node --check projects/frontend/modules/stream.js \
  projects/frontend/modules/panels.js \
  projects/frontend/modules/events.js \
  projects/frontend/modules/commands.js
echo "JS OK"

## 5. Never commit these files
# memory/runtime_state.json
# memory/mood_state.json
# memory/burry_session.json
# memory/rl_experience.json
# memory/long_term_memory.json
# memory/layers/graph.json
# tasks/
# memory/knowledge_base/

## 6. Hook safety check (if backbone changed)
grep -n "get_compressed_context\|_call(\|ollama\|LLM" \
  brain/agentscope_backbone.py | grep -i "hook\|pre_reply\|post_reply"
# PASS: nothing found
# FAIL: you put an LLM call inside a hook — remove it
