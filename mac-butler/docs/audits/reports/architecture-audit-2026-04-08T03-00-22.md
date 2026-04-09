# Mac Butler Architecture Audit

Generated: 2026-04-08T03:00:23.036676+05:30

## Working Tree

```bash
 M .claude/AGENTS.md
 M .claude/ARCHITECTURE.md
 M .claude/CHECKLIST.md
 M .claude/SPRINT_LOG.md
 M agents/runner.py
 M brain/agentscope_backbone.py
 M brain/ollama_client.py
 M butler.py
 M butler_config.py
 M executor/engine.py
 M intents/router.py
 M memory/agentscope_logs/agentscope.log
 M memory/knowledge_base.py
 M memory/layers/graph.json
 M memory/long_term.py
 M memory/long_term_memory.json
 M memory/mood_state.json
 M memory/rl_experience.json
 M memory/runtime_state.json
 M projects/dashboard.py
 M projects/frontend/modules/commands.js
 M projects/frontend/modules/panels.js
 M projects/frontend/modules/stream.js
 M projects/frontend/style.css
 M projects/projects.json
 M runtime/__init__.py
 M runtime/telemetry.py
 M runtime/tracing.py
 M state.py
 M tasks/tasks.json
 M tests/test_butler_pipeline.py
 M tests/test_dashboard.py
 M tests/test_executor.py
 M tests/test_intent_router.py
 M tests/test_next_sprint.py
 M tests/test_ollama_client.py
 M tests/test_remaining_items.py
 M tests/test_runtime_telemetry.py
 M tests/test_tts.py
 M trigger.py
?? docs/audits/
?? docs/phases/
?? memory/burry_session.json
?? memory/knowledge_base/
?? memory/logs/
?? memory/plan_notebook.json
?? runtime/log_store.py
?? scripts/run_architecture_audit.sh
?? tests/test_background_lane.py
?? tests/test_instant_lane.py
```

## Ollama Models

```bash
```

## Effective Routed Models

```text
BUTLER
voice -> gemma4:e4b
planning -> gemma4:e4b
vision -> gemma4:e4b
review -> deepseek-r1:14b
coding -> deepseek-r1:14b

AGENTS
news -> deepseek-r1:14b
market -> deepseek-r1:14b
hackernews -> gemma4:e4b
reddit -> gemma4:e4b
github_trending -> gemma4:e4b
vps -> deepseek-r1:14b
memory -> gemma4:e4b
code -> deepseek-r1:14b
search -> deepseek-r1:14b
github -> deepseek-r1:14b
bugfinder -> gemma4:e4b
```

## Config Drift

```text
INSTALLED

CONFIGURED_BUT_MISSING
deepseek-coder:6.7b
deepseek-r1:14b
deepseek-r1:7b
gemma4:e4b
glm-4.7-flash:latest
llama3.2-vision
llama3.2:3b
phi4-mini:latest
qwen2.5-coder:14b
```

## Targeted Regression Suite

```bash
........................................................................ [ 35%]
........................................................................ [ 70%]
............................................................             [100%]
204 passed in 2.82s
```

## CLI Smoke

```bash
[Skills] Loaded: calendar_skill (3 patterns)
[Skills] Loaded: email_skill (3 patterns)
[Skills] Loaded: imessage_skill (2 patterns)
[Butler would say]: I'm good. What do you need?
[MCP] Failed to load brave: brave MCP not ready: {'name': 'brave', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-brave-search'], 'missing_env': ['BRAVE_API_KEY'], 'ready': False}
[MCP] Failed to load github: github MCP not ready: {'name': 'github', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-github'], 'missing_env': ['GITHUB_PERSONAL_ACCESS_TOKEN'], 'ready': False}
[Memory] Restored session state from disk.
[Backbone] All 5 AgentScope lifecycle hooks registered
[Memory] Saved 15 turns to session file.
[Skills] Loaded: calendar_skill (3 patterns)
[Skills] Loaded: email_skill (3 patterns)
[Skills] Loaded: imessage_skill (2 patterns)
[Butler would say]: Checking the latest news.
[MCP] Failed to load brave: brave MCP not ready: {'name': 'brave', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-brave-search'], 'missing_env': ['BRAVE_API_KEY'], 'ready': False}
[MCP] Failed to load github: github MCP not ready: {'name': 'github', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-github'], 'missing_env': ['GITHUB_PERSONAL_ACCESS_TOKEN'], 'ready': False}
[Agent/news] Using model: None
[Memory] Restored session state from disk.
[Backbone] All 5 AgentScope lifecycle hooks registered
[Memory] Saved 15 turns to session file.
[Skills] Loaded: calendar_skill (3 patterns)
[Skills] Loaded: email_skill (3 patterns)
[Skills] Loaded: imessage_skill (2 patterns)
[MCP] Failed to load brave: brave MCP not ready: {'name': 'brave', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-brave-search'], 'missing_env': ['BRAVE_API_KEY'], 'ready': False}
[MCP] Failed to load github: github MCP not ready: {'name': 'github', 'enabled': False, 'configured': True, 'command': ['npx', '-y', '@modelcontextprotocol/server-github'], 'missing_env': ['GITHUB_PERSONAL_ACCESS_TOKEN'], 'ready': False}
[Memory] Restored session state from disk.
[Backbone] All 5 AgentScope lifecycle hooks registered
[Butler would say]: Going quiet. Say wake up to start again.
[Memory] Saved 15 turns to session file.
```
