# Butler Engineering Audit
Last updated: 2026-04-09T01:38:00+0530
Status: IN PROGRESS

## Critical Bugs (break core experience)
| # | Issue | Root Cause | File | Fix | Size |
| --- | --- | --- | --- | --- | --- |
| 1 | `play music on youtube` plays on Spotify | `clean_song_query()` strips `on youtube`, then the generic `play` regex falls straight into `spotify_play`. The new semantic override only patches over this router bug. | `intents/router.py:379-387`, `intents/router.py:853-861`, `capabilities/planner.py:61-74` | Make provider/source a first-class field in the task schema and route media requests to `media_play(provider=...)` before Spotify defaults. | M |
| 2 | `create folder on Desktop` creates the wrong path and can include `on desktop` in the name | The legacy folder route captures only one token after `folder` and hardcodes `~/Developer/...`, so `create folder on desktop ...` becomes `~/Developer/on`. Executor then blindly creates whatever path it receives. | `intents/router.py:903-905`, `executor/engine.py:857-861`, `capabilities/resolver.py:55-83` | Delete the legacy hardcoded folder regex and always resolve folder name + location through a path resolver before execution. | S |
| 3 | `latest news on Claude Mythos` returns nothing | News is architected as a background lane that speaks an acknowledgement and fires `run_agent_async()` with no callback into final TTS. If the agent has thin coverage, it falls back to a generic failure string. | `pipeline/router.py:400-429`, `agents/runner.py:892-918`, `agents/runner.py:1060-1128` | Treat news as a synchronous lookup lane with a deadline and exactly one final spoken result, or attach an async callback that speaks and records completion. | M |
| 4 | `open terminal` opens two terminals | `open terminal` routes as `open_app(Terminal)`, which special-cases into `open_terminal("tab")`. When Terminal is not running, `open_terminal()` switches to `launch`, calls `activate`, then `do script`, which can create the default Terminal window plus the scripted one. | `intents/router.py:989-1006`, `executor/engine.py:600-617`, `executor/engine.py:397-410` | Split `focus/open Terminal` from `run command in Terminal`. Cold launch should use a single-window open path, not the command-tab helper. | S |
| 5 | `write mail to X with subject Y body Z` can open Gmail with fields missing | Email composition is regex-only and returns `compose_email` even when parsing is partial or empty. `_gmail_compose_url()` silently opens blank Gmail when params are missing. There is no required-arg validation. | `intents/router.py:556-622`, `intents/router.py:849-851`, `intents/router.py:657-673` | Validate recipient/subject/body before returning `compose_email`; if parsing is partial, keep slot state and ask one clarification instead of opening blank Gmail. | M |
| 6 | Butler forgets what was said 5 seconds ago | Conversation state exists, but it is mostly prompt text, not executable state. Instant/background lanes return before conversation resolution, and pending dialogue only handles `spotify_song` and `file_name`. | `pipeline/recorder.py:25-92`, `pipeline/router.py:145-182`, `pipeline/router.py:596-633`, `pipeline/router.py:655-669` | Add typed turn state and slot filling across intents so follow-ups are resolved before lane selection, not only inside prompts. | L |
| 7 | `with subject hello` after an email command routes as `unknown` | There is no pending email dialogue state. `_resolve_pending_dialogue()` only supports Spotify song clarification and file naming, so standalone email follow-ups fall through to `unknown` `0.0`. | `pipeline/router.py:145-182`, `intents/router.py:1033` | Add `pending_email` slots for recipient/subject/body and merge follow-up utterances into the prior draft intent. | M |
| 8 | No startup briefing on wake with GitHub/weather/tasks/calendar | Startup briefing code exists, but it only summarizes recent sessions and current project state. Wake intent just says `I'm listening.` and never triggers the briefing. Weather/calendar/GitHub push data are not collected at all. | `pipeline/router.py:290-295`, `butler.py:534-562`, `butler.py:1477-1498`, `butler.py:1686-1688` | Run briefing on wake/session start and build a real startup aggregator for GitHub pushes, weather, tasks, and calendar. | M |
| 9 | No real conversation mode | Freeform chat is squeezed into `question`/`unknown` fallbacks with short-answer prompts and tool-first policies. There is no dedicated brainstorm/discussion mode or long-form dialogue contract. | `intents/router.py:1022-1033`, `pipeline/orchestrator.py:104-115`, `pipeline/orchestrator.py:141-145`, `pipeline/orchestrator.py:190-214`, `pipeline/orchestrator.py:718-719` | Add a dedicated dialogue lane with richer prompts, longer response budgets, and explicit tool/no-tool decisioning. | L |
| 10 | No filesystem CRUD by voice | The executor has `write_file`, but the voice/router layer only exposes `create_file` and `create_folder`. There are no routed read/delete intents and no safe file capability surface. | `executor/engine.py:926-938`, `intents/router.py:896-905`, `capabilities/registry.py:113-194` | Add explicit `read_file`, `write_file`, `delete_file`, and `list_path` tools plus confirmation rules for destructive actions. | L |
| 11 | Router returns `unknown` with `0.0` instead of understanding intent | `route()` is still regex-first and falls back to `Intent("unknown", confidence=0.0)`. The semantic planner is layered after routing, not the primary classifier. | `intents/router.py:1011-1033`, `pipeline/router.py:596-603`, `pipeline/router.py:708-763`, `capabilities/planner.py:252-256` | Make semantic planning the front door and keep regex routing as fast-path guardrails only. | L |
| 12 | Spoken email parsing like `at the red gmail com` breaks | `normalize_email()` can normalize `at the red`, but `_extract_compose_email_params()` strips recipient text at noise words like `the`, so the full address never reaches normalization. Direct probe currently yields recipient `vedang2803`. | `intents/router.py:590-604`, `contact_utils.py:25-64` | Stop stripping recipient fragments before normalization; parse recipient spans structurally, then normalize the full spoken address. | S |
| 13 | Volume control reported missing | Current code already has system and Spotify volume controls, but they are split across separate routes and not surfaced as one coherent capability. This is a coverage/documentation gap more than a missing executor. | `intents/router.py:812-821`, `intents/router.py:882-884`, `executor/engine.py:811-823`, `executor/engine.py:1123-1138` | Keep the existing actions, add semantic coverage/tests, and expose one unified `set/adjust volume` capability. | S |
| 14 | Browser tab control reported missing | New-tab and close-tab/window actions already exist, but only narrow phrasings are covered and there is no semantic layer or user-facing documentation proving the feature is available. | `intents/router.py:750-770`, `executor/engine.py:1029-1095` | Preserve the existing executor paths and add semantic/tab-object routing plus regression tests for natural phrasing. | S |
| 15 | WhatsApp sending feels missing | There is a route and executor path, but the parser order is wrong and captures `to vedang` as the contact. If no phone resolves, `whatsapp_send` only opens WhatsApp Web instead of actually sending. | `intents/router.py:625-653`, `intents/router.py:801-804`, `executor/engine.py:1154-1164` | Reorder WhatsApp regexes, resolve contacts/phones before execution, and separate `compose WhatsApp` from `send WhatsApp`. | M |

## Architecture Gaps (missing systems)
| # | Gap | Why Missing | Files to Create | Size |
| --- | --- | --- | --- | --- |
| 1 | First-class semantic planner | Intent understanding still starts in regex routing, so natural phrasing is always best-effort recovery after failure. | `planner/semantic_router.py`, `planner/task_schema.py`, `planner/tool_policy.py` | L |
| 2 | Cross-turn slot memory | Conversation history is recorded, but there is no typed slot state for drafts, references, or unfinished tasks. | `conversation/session_state.py`, `conversation/slots.py`, `tests/test_followup_slots.py` | L |
| 3 | Startup intelligence aggregator | Wake/startup has no structured source for weather, GitHub activity, tasks, or calendar. | `startup/briefing.py`, `startup/providers.py`, `tests/test_startup_briefing.py` | M |
| 4 | Real dialogue lane | Brainstorming and normal discussion are treated as short command-adjacent answers instead of a dedicated mode. | `dialogue/manager.py`, `dialogue/prompts.py`, `tests/test_dialogue_mode.py` | L |
| 5 | Filesystem voice tools | Safe file read/write/delete/list capabilities are not modeled as tools. | `tools/filesystem.py`, `capabilities/filesystem.py`, `tests/test_filesystem_voice.py` | L |
| 6 | Capability regression pack | Many features exist in executor code but are invisible or stale because phrase-level regression tests are sparse. | `tests/test_phrase_regressions.py`, `tests/test_tool_registry_contracts.py` | M |

## Quick Wins (under 30 min each)
- Fix `open terminal` cold-launch behavior so it opens exactly one Terminal window.
- Reorder WhatsApp regex matching so `send whatsapp to vedang ...` does not keep the `to`.
- Validate `compose_email` args before opening Gmail; clarify when recipient parsing is empty.
- Add `pending_email` dialogue state so `with subject hello` continues the previous draft.
- Add regression tests for `play ... on youtube`, Desktop folders, spoken email addresses, and news follow-ups.
- Document that volume and browser-tab control already exist, then add phrase tests so they stay working.

## Implementation Order
1. Make semantic planning the primary front door, with regex routing as fast-path only.
2. Add cross-turn slot memory for email, folders, media, and task/calendar follow-ups.
3. Convert lookup/news/current-facts into synchronous deadline-bounded turns with guaranteed final speech.
4. Fix high-friction command bugs: Terminal duplicate open, spoken email parsing, WhatsApp parser ordering, Desktop folder paths.
5. Build a real startup briefing pipeline for wake/session start with GitHub, weather, tasks, and calendar.
6. Add dedicated dialogue mode for brainstorm/discussion instead of short command-style replies.
7. Add safe filesystem CRUD capabilities and confirmation rules.
8. Backfill phrase-level regression tests and capability docs.

## What Was Fixed This Session
- Search fallback was fixed in `agents/runner.py`: `_fetch_search_text()` now tries SearXNG first, then Exa when configured, then DuckDuckGo, and returns reranked fetched content from the first backend that works.
- Background-lane `news` was changed in `pipeline/router.py` from fire-and-forget async dispatch to synchronous `run_agent("news", ...)` so the news turn now produces one final spoken result.
- YouTube media routing was fixed in `intents/router.py`: explicit platform detection now runs before `clean_song_query()` strips provider text, so `play ... on youtube` no longer falls through to Spotify.
- Email multi-turn continuity was added in `pipeline/router.py`: `compose_email` now sets `pending_email` when subject/body is missing, and follow-ups fill `subject` then `body` before producing the final Gmail compose action.
- Email follow-up phrasing was widened in `butler.py` by adding prefixes like `with subject`, `subject is`, `body is`, `the body says`, and `message is`.
- Per the latest user instruction, no new Ollama models were pulled and the Gemma voice/planning model configuration was left unchanged.

## What Still Needs Work
- Router is still regex-first and still returns `unknown` `0.0` when patterns miss.
- Cross-turn continuity is still limited to a small number of hardcoded pending-dialogue cases even after `pending_email`.
- `venv/bin/python butler.py --test` still ends with `[Butler would say]: Something went wrong.` in direct verification, despite local Ollama being reachable.
- Startup briefing still does not run on wake and still lacks weather/calendar/GitHub signals.
- Conversation mode, filesystem CRUD, and contact/calendar systems still need real architecture, not more patches.
