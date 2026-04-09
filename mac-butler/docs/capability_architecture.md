# Capability Architecture

## Goal

Move Butler from phrase-first routing to a capability-driven flow:

`user request -> semantic task -> validated tool call -> deterministic executor -> final spoken reply`

## Current Dependency Boundary

- `executor/engine.py` remains the side-effect layer.
- `intents/router.py` still handles existing deterministic instant commands.
- `pipeline/router.py` now imports the capability layer and can override weak or incorrect routes before execution.
- `capabilities/` is the new semantic layer:
  - `contracts.py`: typed task/tool/event contracts
  - `registry.py`: canonical tool surface over existing executor actions
  - `resolver.py`: runtime-aware argument resolution
  - `planner.py`: semantic planning and override logic

## Why This Boundary Matters

Changing `executor/engine.py` directly risks breaking existing system actions.
The current refactor avoids that by changing decision-making above the executor:

- keep executor behavior
- keep existing router for narrow fast lanes
- add semantic recovery / override for missed natural phrases
- add synchronous lookup execution where final spoken output matters

## Current Semantic Coverage

The new planner currently covers these user-reported misses:

- `minimize this window`
- natural Desktop folder creation
- `check my vps`
- weather phrasing like `search weather in mumbai`
- `play <song> on youtube`
- `latest ai news` as a synchronous lookup path instead of background-only acknowledgement

## Runtime Behavior

Planner output is validated through the tool registry before execution.

- control tasks map to existing executor actions
- lookup tasks can run synchronously to guarantee one final answer
- clarification tasks stay in dialogue instead of falling back to hardcoded junk

## Dependency Impact Of Current Refactor

- `pipeline/router.py` is the only existing runtime file changed so far.
- `executor/engine.py` is unchanged.
- `intents/router.py` is unchanged.
- New tests pin the new semantic path without rewriting the legacy suite.

This keeps blast radius low while moving the architecture in the right direction.
