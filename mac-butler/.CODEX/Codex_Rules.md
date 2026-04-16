## BURRY OS — Codex Engineering Rules
Read before every session. Follow every rule.

Implementation root: `mac-butler/`

## First principles

- Extend an existing owner before creating a new file
- If a new file does not own a genuinely new domain, do not create it
- Keep one owner per core subsystem
- Treat code, tests, `.CODEX/Codex.md`, `docs/phases/PHASE.md`, and `docs/phases/PHASE_PROGRESS.md` as the live hierarchy

## Owner map — one of each

- classifier/router: `intents/router.py`
- pipeline entry + lane selector: `pipeline/router.py`
- multi-step orchestration: `pipeline/orchestrator.py`
- tool registry: `brain/tools_registry.py`
- LLM caller: `brain/ollama_client.py`
- executor: `executor/engine.py`
- hot-path memory write: `memory/bus.py`
- session memory: `brain/session_context.py`
- HUD/API surface: `projects/dashboard.py`

Creating a second version of any of these is almost always wrong.

## Never do these

- Never call an LLM inside a hook
- Never use `asyncio.run()` inside AgentScope tools or agents
- Never make `_ws_broadcast()` blocking
- Never call `agentscope.init()` more than once
- Never create a second router, tool registry, LLM caller, or hot-path memory writer
- Never remove the instant-pattern fast path
- Never add a feature without wiring it through route, tool, verification, narration, and tests
- Never let current-information features answer from thin model context if a real public-data fallback can be added
- Never pass enum-like values between owners without normalizing them at the boundary
- Never call a provider abstraction complete while hard-coded model names or raw transport calls still exist elsewhere in the runtime
- Never commit runtime state files under `memory/`, `tasks/`, or other generated artifacts

## Code patterns

- Executor dispatch stays table-driven in `executor/engine.py`
- `pipeline/router.py` stays a wrapper and lane selector, not an intent classifier
- New exact user phrases become regressions in the relevant router, executor, or pipeline tests
- Public API and WebSocket contract changes stay versioned under `/api/v1/...` and the typed DTO layer

## Validation rules

- Run targeted `py_compile` and pytest coverage for every touched owner
- Run dashboard, A2A, contract, or frontend checks when the public surface changes
- Run host smoke or explicit manual checks when changing host-operating actions
- Docs-only corrections still require a readback pass across the touched `.CODEX` and phase files

## Quality bar

- Build for real user flows, not just mocked happy paths
- Prefer one good regression for the exact broken phrase over broad shallow assertions
- If a fix changes runtime truth, update `.CODEX/Codex.md`, `.CODEX/SPRINT_LOG.md`, `.CODEX/Learning_loop.md`, `.CODEX/Capability_Map.md` when applicable, `docs/phases/PHASE_PROGRESS.md`, and `README.md` when user-facing behavior changes
