# Burry OS — Architecture Map
Status: live Phase 3 architecture
Last updated: 2026-04-12

Workspace root: `/Users/adityatiwari/Burry`
Implementation root: `mac-butler/`

## Entry points

- `butler.py` — main runtime orchestration
- `trigger.py` — clap/keyboard trigger path and fresh-session reset
- `projects/dashboard.py` — HUD server plus `/api/v1/...` surface
- `channels/a2a_server.py` — backend command/listen/interrupt surface

## Hot path

`trigger -> briefing -> STT -> pending -> instant -> skills -> classifier -> lane -> tool/agent -> verify -> memory bus -> speech`

The hot path must stay deterministic and truthful:

- pending follow-up resolves before new intent work
- instant patterns stay ahead of skills and classifier work
- the classifier returns typed intent, params, and confidence
- direct actions use typed executor calls
- side effects are verified before narration
- `memory/bus.py` is the only hot-path writer

## Lane ownership

- `Talk`: lightweight replies and conversation, primarily through `pipeline/router.py` plus `brain/conversation.py`
- `Do`: direct typed actions through `intents/router.py` and `executor/engine.py`
- `Figure it out`: planner/research paths through `pipeline/orchestrator.py`, `agents/planner_agent.py`, `agents/research_agent.py`, and `agents/runner.py`

`pipeline/router.py` chooses the lane.
It does not replace `intents/router.py`.

## Provider layer

- `butler_config.py` is the source of truth for provider-tagged model roles and speech backends
- `brain/ollama_client.py` is the single LLM caller for both local Ollama and the OpenAI-compatible NVIDIA surface
- `voice/tts.py` follows `nvidia_riva_tts -> kokoro -> edge -> say`
- `voice/stt.py` follows `nvidia_riva_asr -> mlx -> faster-whisper`
- provider fallbacks must remain truthful when NVIDIA credentials or host clients are absent

## Execution surfaces

- `executor/engine.py` owns direct actions and their verification-aware narration
- `agents/runner.py` owns specialist current-info and utility agents such as news, market, GitHub, and VPS helpers
- `agents/browser_agent.py` owns browser-specific higher-order browsing work
- `projects/open_project.py` owns editor fallback selection

## Memory, telemetry, and contracts

- `brain/session_context.py` owns pending state and recent turn memory
- `memory/bus.py` is the only hot-path write path
- `runtime/telemetry.py` publishes HUD-facing runtime events
- dashboard and A2A public HTTP routes are versioned under `/api/v1/...`
- HUD WebSocket events use the versioned envelope: `event_version`, `type`, `ts`, `data`

## Active Phase 3 runtime truth

- provider-aware LLM, TTS, and STT routing is live
- page summarization falls back from Jina to direct HTML extraction
- video summarization falls back through caption tracks, transcripts, `yt-dlp`, Whisper, and page extraction
- news uses SearXNG, DuckDuckGo, Exa, then Google News RSS before giving up
- calendar read supports today, tomorrow, next event, and week-style reads with truthful permission failure

## Guardrails

- no second router, tool registry, LLM caller, or hot-path memory writer
- no LLM calls inside hooks
- no blocking HUD broadcast on the hot path
- no feature is complete until route, execution, verification, narration, tests, and live docs all agree
