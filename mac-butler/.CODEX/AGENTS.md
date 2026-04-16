# Burry OS — Agent Operating Rules
Read this before touching code.

Workspace root: `/Users/adityatiwari/Burry`
Implementation root: `mac-butler/`

## Core owners

- `intents/router.py` is the primary classifier/router owner
- `pipeline/router.py` is the wrapper plus lane selector, not a second router
- `pipeline/orchestrator.py` owns planner/research orchestration
- `brain/ollama_client.py` is the single LLM caller
- `brain/tools_registry.py` is the single tool registry
- `brain/session_context.py` owns pending state and turn memory
- `memory/bus.py` is the only hot-path memory write path
- `executor/engine.py` owns typed direct actions
- `projects/dashboard.py` owns the HUD/API surface

Extend these owners before creating new modules.

## Routing contract

Burry is a local natural-language agent with a strict hot path:

1. `trigger.py` resets session state and starts briefing
2. STT produces text
3. `brain/session_context.py` resolves pending follow-up first
4. instant patterns run before any skill or classifier work
5. skills run after an instant miss and before the classifier
6. the configured classifier returns typed `intent + params + confidence`
7. high-confidence direct actions go to `executor/engine.py`
8. medium confidence asks one clarification
9. low confidence falls into conversation mode
10. `memory/bus.py` records asynchronously
11. speech narrates the verified outcome

Do not reorder this without code, tests, and docs moving together.

## Non-negotiable rules

- No LLM calls inside hooks
- No `asyncio.run()` inside AgentScope tools or agents
- No blocking WebSocket broadcast on the hot path
- No second router, second tool registry, second LLM caller, or second hot-path memory writer
- No feature is shipped without `route -> tool -> verify -> narrate -> tests`
- No stale doc is allowed to override code, tests, `.CODEX/AGENTS.md`, `.CODEX/Codex.md`, `docs/phases/PHASE.md`, or `docs/phases/PHASE_PROGRESS.md`
- No current-information feature should fall back to model-only narration if a public data fallback can be added
- No enum-like router param should cross an owner boundary without normalization and a regression test

## Runtime shape

- Provider selection is config-driven from `butler_config.py`
- Fast voice, classifier, and conversation roles are NVIDIA-first with local Ollama fallback
- Planning and coding roles are provider-aware and must stay behind `brain/ollama_client.py`
- TTS follows `nvidia_riva_tts -> kokoro -> edge -> say`
- STT follows `nvidia_riva_asr -> mlx -> faster-whisper`
- `gemma4:26b` remains a VPS-only fallback, not the local voice hot path

## Validation floor

- Run targeted compile and pytest coverage for every touched owner
- When contracts, dashboard, A2A, or telemetry change, run the relevant API/frontend regression slice
- When host actions change, run `venv/bin/python scripts/system_check.py --json --phase1-host --phase1-host-only`, `venv/bin/python scripts/system_check.py --json --phase3a-host --phase3a-host-only`, or explicit manual host checks
- Update `.CODEX/AGENTS.md` when operating rules, owner maps, or validation-floor guidance change; update `.CODEX/Codex.md`, `.CODEX/SPRINT_LOG.md`, `.CODEX/Learning_loop.md`, `.CODEX/Capability_Map.md` when runtime truth changes, `docs/phases/PHASE_PROGRESS.md`, and `README.md` when user-facing behavior changes
