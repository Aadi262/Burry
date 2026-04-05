# Multi-Agent Spec

Source note: reconstructed from the user-provided prompt chain because the original referenced document index was not locally accessible during the audit.

## Scope

Major upgrade to Mac Butler at `/Users/adityatiwari/Burry/mac-butler`.

This upgrade adds:

1. Multi-model specialist agent system
2. Web search and news tool support
3. VPS and Docker management agent
4. KAIROS-inspired background heartbeat
5. Confirmation gate for dangerous actions

## Part 1: Specialist Agent System

### `agents/runner.py`

- Route different tasks to different Ollama models:
  - `news` -> `deepseek-r1:7b`
  - `vps` -> `qwen2.5-coder:7b`
  - `memory` -> `phi4-mini`
  - `code` -> `qwen2.5-coder:14b`
  - `search` -> `deepseek-r1:7b`
- Fallback to the main model when specialist models are unavailable.
- Provide structured result objects: `{"status": ..., "result": ..., "data": ...}`.

### Agent Behaviors

- `news`: fetch and summarize recent news.
- `search`: answer search-style questions from fetched material.
- `vps`: inspect Docker, disk, memory, and uptime over SSH.
- `memory`: compress session history into short memory points.
- `code`: generate or review code from a task prompt.
- Optional GitHub and bugfinder style agents may also exist.

## Part 2: KAIROS Heartbeat

### `daemon/heartbeat.py`

- Run quietly every few minutes.
- Ask whether there is anything worth surfacing.
- Only safe low-risk actions are allowed automatically:
  - `notify`
  - `remind_in`
  - `obsidian_note`

## Part 3: Confirmation Gate

### `executor/engine.py`

- Add `_requires_confirmation`.
- Add `_ask_confirmation`.
- Guard dangerous actions:
  - `git push`
  - destructive Docker commands
  - destructive SSH commands
  - overwrite file writes

## Part 4: Wire Agents Into Butler

- Orchestrator must be able to emit `run_agent` actions.
- Executor must dispatch those actions through `agents.runner`.
- Agent results should feed back into final spoken output.

## Part 5: Setup

- Pull specialist models where available.
- Butler should degrade gracefully if models are missing.

## Expected Outcome

- Deterministic commands stay fast.
- Complex queries route through the orchestrator and specialist agents.
- VPS/news/search style requests no longer depend on generic one-shot fallback speech.
- Dangerous actions require confirmation.
