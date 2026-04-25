# BURRY OS — Capability Map
Last updated: 2026-04-26
Legend: `✅ working` | `🟡 partial` | `❌ not built` | `🔧 needs your setup`

This file now has 2 layers:
- the override sections record the current runtime truth for capabilities that have moved since the original backlog table was created
- the full inventory keeps every capability ID in one readable place so planning does not drop anything

When a full-inventory row conflicts with an override or with recent code and tests, the override is authoritative.

## Inventory Snapshot

The old compact map claimed `150` total capabilities, but the live inventory actually contains `156` tracked IDs.

| Metric | Count |
| --- | ---: |
| Working capabilities | 40 |
| Partial capabilities | 80 |
| Not built capabilities | 34 |
| Setup-dependent-only capabilities | 2 |
| Capabilities that still touch setup prerequisites | 7 |
| Total capability IDs tracked | 156 |

## Phase 2 Public Contract IDs

| ID | Public tool | Current contract meaning |
| --- | --- | --- |
| B09 | `play_youtube` | YouTube play/search handoff |
| B10 | `lookup_page` | current page or URL read lookup |
| E03 | `compose_email` | Gmail compose draft path |
| F04 | `create_folder` | path-aware folder creation |
| K01 | `lookup_web` | current web lookup |
| K03 | `lookup_news` | current news lookup |
| K04 | `lookup_weather` | weather lookup |
| K09 | `lookup_project_status` | tracked project-status lookup |
| K10 | `lookup_github_status` | GitHub repo-status lookup |
| SY14 | `minimize_app` | frontmost-window minimize |
| T14 | `check_vps` | VPS health lookup |

## Current-Truth Overrides

### Phase 1 hardening

| IDs | Status | Current truth |
| --- | --- | --- |
| B09, E03, E04, E08, W02, W05, M06 | mixed | YouTube play/search, Gmail compose plus attachment drafts, and WhatsApp compose/file-share flows are wired enough to be truthful, but they still stop short of guaranteed autoplay or delivery |
| T01 | ✅ | Plain `open terminal` now opens a fresh Terminal window in the covered path; focus-only behavior is reserved for explicit focus semantics |
| C01-C06 | mixed | calendar read, calendar add, reminders, task read, and task add all moved forward on the existing owners; live calendar reads and writes still require Calendar automation access, while reminders verify when Reminders automation is available |
| I01-I02, I05 | mixed | pending dialogue memory is real for the compose flow; general conversation exists, but dedicated brainstorm behavior is still shallow |
| H10, H12, H13 | mixed | memory and pending events now publish, recent Notification Center activity is ingested into runtime/HUD truth through unified-log reads, and project cards stay aligned with tracked live focus; mood events exist but the HUD presentation is still thinner than the backend signal |

### Phase 3 feature completion

| IDs / slice | Status | Current truth |
| --- | --- | --- |
| Provider-aware LLM/TTS/STT routing | 🟡 | config-driven provider selection is live across classifier, conversation, briefing, planner, search, browser, research, heartbeat, bug-hunter, TTS, and STT roles; optional DeepSeek/Kimi OpenAI-compatible endpoints are now wired, local Ollama fallback skips under low-RAM pressure, and retrieval roles like weather/project-status/page-read stay NVIDIA-first by default |
| B02, B13, B14 | 🟡 | browser new-window, back, and refresh phrases now route deterministically, execute on the resolved browser family, and are host-smoke validated against local temp pages; plain running-browser app opens now force a fresh visible browser window |
| F01-F15 | 🟡 | filesystem routing now covers common local create/open/read/write/find/list/move/copy/rename/delete/zip phrases on Desktop/Documents/Downloads/Home-style aliases; delete remains confirmation-gated and broader naming variants are still thinner than the core paths |
| SY01-SY09, SY11, SY17-SY20 | 🟡 | system-control routing now covers common volume or mute, brightness, screenshot, lock-screen, sleep, show-desktop, dark-mode, do-not-disturb, and battery or wifi phrases; safe host smoke now covers screenshot/battery/wifi while disruptive controls remain operator-gated |
| C01-C04 | mixed | calendar reads and writes now use truthful Calendar host-permission fallback when automation is unavailable, and reminders verify against the Reminders list when automation access is granted |
| K03 | 🟡 | news uses SearXNG, DuckDuckGo, Exa, then Google News RSS before giving up; NVIDIA Gemma E4B is the hot text model, larger NVIDIA models remain in fallback, and timeout filler is rejected before speech |
| B10, B16, K06 | 🟡 | current-page reads plus page summarization now reuse indexed web-page snapshots from `memory/knowledge_base.py`, resolve the active browser URL when needed, and fall back through Jina or direct HTML extraction |
| K09, K10 | 🟡 | tracked project status now summarizes derived project health, blockers, next tasks, and adjacent GitHub repo state; direct GitHub status still works for tracked projects and raw `owner/repo` phrases |
| M09, K07, M10 | 🟡 | video summarization now has caption and transcript fallbacks and can save notes into Obsidian when configured |
| Live voice session loop | 🟡 | continuous clap sessions now gate STT on actual TTS playback and drop recent spoken-text echoes before dispatch; startup briefing weather now comes from a speech-safe provider format instead of the emoji-heavy default line, but broader barge-in and audio-ducking behavior still needs live tuning |

## Full Inventory

### Browser Control

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| B01 | Open new tab | open new tab | 🟡 | AppleScript path still needs broader host validation |
| B02 | Open new window | open new window | 🟡 | deterministic new-window route is live; executor opens a new window on the resolved browser family and the Phase 3A host smoke validates it against local temp pages |
| B03 | New tab even if Chrome open | new tab | 🟡 | running-browser app opens now force a fresh visible browser window for covered Chrome-family apps; cross-browser tab-state checks remain thinner |
| B04 | Close current tab | close this tab | 🟡 | route and executor exist, but verification is still AppleScript-only |
| B05 | Close current window | close this window | 🟡 | close-window route and executor path exist, but host-smoke validation is still thin |
| B06 | Go to URL | go to github.com | ✅ | working |
| B07 | Google search | search for X | ✅ | working |
| B08 | YouTube search | search X on youtube | ✅ | routes to the YouTube results page instead of falling into Spotify |
| B09 | Play on YouTube | play X on youtube | 🟡 | opens verified YouTube search/results flow for `play X on youtube`; it does not guarantee autoplay |
| B10 | Read current page | read this page | 🟡 | `lookup_page` now resolves the active browser URL from runtime context and reads it through the indexed fetch path; it still depends on current browser state or an explicit URL being available |
| B11 | Scroll down | scroll down | ❌ | needs vision or GUI control stack, not just browser URL wiring |
| B12 | Click button | click submit button | ❌ | needs vision plus GUI control |
| B13 | Go back | go back | 🟡 | deterministic back route is live, runs against the resolved browser family, and is host-smoke validated against local temp pages |
| B14 | Refresh page | refresh | 🟡 | deterministic refresh route is live, runs against the resolved browser family, and is host-smoke validated against local temp pages |
| B15 | Open incognito | open incognito | ❌ | not built |
| B16 | Summarize page | summarize this page | 🟡 | `summarize_page` now reuses indexed page snapshots before falling back to Jina and direct HTML extraction for ordinary web pages |
| B17 | Open Google Docs | open google docs | ✅ | mapped in the router and executor to `https://docs.new` |
| B18 | Open Google Sheets | open google sheets | ✅ | mapped in the router and executor to `https://sheets.new` |
| B19 | Open Google Meet | open google meet | ✅ | mapped in the router and executor to `https://meet.new` |
| B20 | Open Google Slides | open google slides | ✅ | mapped in the router and executor to `https://slides.new` |

### Files and Folders

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| F01 | Create file on Desktop | make file on desktop | 🟡 | create-file actions exist, but natural Desktop-targeted phrasing is still thinner than the new read/write/open flows |
| F02 | Create file in Downloads | new file in downloads | 🟡 | deterministic Downloads-targeted create-file phrasing now lands on `~/Downloads/untitled.txt`; broader naming variants are still thinner |
| F03 | Create folder on Desktop | create folder called Work | 🟡 | covered folder-create phrasing now strips location words out of the folder name |
| F04 | Create folder in specific path | new folder in documents | 🟡 | documents/downloads/home aliases now resolve cleanly in the covered folder-create path, but host smoke is still thin |
| F05 | Open/find file | open budget.xlsx | 🟡 | deterministic open-file routing and fuzzy local-path resolution now exist; Finder reveal depth is still shallow |
| F06 | Read file contents | read my notes file | 🟡 | deterministic read-file routing now resolves common local file names through search roots |
| F07 | Write to file | write hello to test.txt | 🟡 | deterministic overwrite-style write flow is wired; richer append/edit phrasing is still limited |
| F08 | Delete file with confirmation | delete that file | 🟡 | delete execution is confirmation-gated and verification-aware, with deterministic phrase coverage and Phase 3A host-smoke validation on explicit paths |
| F09 | Find file by name | find resume file | 🟡 | deterministic find-file routing now searches common local roots by fuzzy name |
| F10 | List files on Desktop | what's on my desktop | 🟡 | deterministic list-files routing exists for common locations like Desktop |
| F11 | Move file | move resume to documents | 🟡 | move-file routing is wired and preserves the filename when the destination is a directory |
| F12 | Copy file | copy to downloads | 🟡 | copy-file routing is wired and preserves the filename when the destination is a directory |
| F13 | Rename file | rename to v2 | 🟡 | rename now routes through the move-file path; broader rename phrasing is still thin |
| F14 | Zip folder | zip this folder | 🟡 | deterministic zip-folder routing, executor support, verification, and Phase 3A host-smoke coverage are now in place |
| F15 | Open Finder at path | open finder at downloads | 🟡 | deterministic open-folder routing exists for common locations like Downloads |
| F16 | Create file via Terminal | open terminal make test.py | ❌ | multi-step path is still broken |
| F17 | Create Google Sheet | open new google sheet | ❌ | still needs explicit create-new routing instead of generic open |
| F18 | Create Google Doc | open new google doc | ❌ | still needs explicit create-new routing instead of generic open |

### Email

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| E01 | Open Gmail | open gmail | ✅ | working |
| E02 | Open compose | compose new email | 🟡 | compose opener is still shallower than the full structured draft path |
| E03 | Send with to/subject/body | email vedang subject X body Y | 🟡 | parses recipient, subject, and body and opens verified Gmail compose; actual send remains operator-driven |
| E04 | Multi-turn compose | write to vedang -> subject -> body | ✅ | pending follow-up flow now merges recipient, subject, and body into one compose draft path |
| E05 | Reply to last email | reply to last email | ❌ | needs a Gmail API or a reliable mailbox integration |
| E06 | Read inbox | read my emails | ❌ | needs a Gmail API or a reliable mailbox integration |
| E07 | Search emails | find emails from vedang | ❌ | needs a Gmail API or a reliable mailbox integration |
| E08 | Send with attachment | attach file and send | 🟡 | attachment-aware compose now prefers a Mail draft with pre-attached files when automation is available and falls back truthfully to Gmail compose when it is not; actual send remains operator-driven |

### WhatsApp

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| W01 | Open WhatsApp | open whatsapp | ✅ | working |
| W02 | Send to contact | whatsapp vedang saying hi | 🟡 | contact and phone phrasing open the WhatsApp message flow truthfully; delivery remains degraded unless explicitly confirmed |
| W03 | Send with phone number | whatsapp +91XXXX hi | 🟡 | still depends on optional GUI-path packages |
| W04 | Read last message | read my last whatsapp | ❌ | no clean supported API on the local-app path |
| W05 | Send file | send resume on whatsapp | 🟡 | file-share phrasing now opens WhatsApp truthfully and reveals resolved files in Finder for manual confirmation; true file delivery verification still needs GUI automation |
| W06 | Open specific chat | open vedang's chat | ❌ | needs GUI automation |
| W07 | Reply to last | reply to last whatsapp saying ok | ❌ | not built |

### Music and Media

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| M01 | Play on Spotify | play blinding lights | ✅ | working |
| M02 | Pause Spotify | pause | ✅ | working |
| M03 | Next song | next song | ✅ | working |
| M04 | Previous song | previous | ✅ | working |
| M05 | Spotify volume | spotify volume 50 | ✅ | working |
| M06 | Play on YouTube | play X on youtube | 🟡 | same behavior as B09; routed away from Spotify, but still result-page based |
| M07 | Play on Apple Music | play X on apple music | ❌ | not handled |
| M08 | Pause YouTube | pause the video | 🟡 | AppleScript path is still unreliable |
| M09 | Summarize YouTube video | summarize this video | 🟡 | `summarize_video` prefers caption tracks and falls back through transcript APIs, `yt-dlp`, local Whisper, and page extraction |
| M10 | Save video notes to Obsidian | save notes from this video | 🟡 | the video-summary flow can save the generated summary into Obsidian when the vault path is configured |
| M11 | What is playing | what song is this | ✅ | working |

### System Control

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| SY01 | Volume up | volume up | 🟡 | deterministic routing and osascript execution exist, but broader host smoke is still thin |
| SY02 | Volume down | volume down | 🟡 | deterministic routing and osascript execution exist, but broader host smoke is still thin |
| SY03 | Set volume | set volume to 50 | 🟡 | deterministic absolute-volume routing is wired through the existing executor path |
| SY04 | Mute | mute | 🟡 | exact mute and natural mute phrases now route to system volume zero instead of falling into media pause |
| SY05 | Brightness up | increase brightness | 🟡 | deterministic brightness-up phrases now route through the existing keyboard-driven executor path |
| SY06 | Brightness down | decrease brightness | 🟡 | deterministic brightness-down phrases now route through the existing keyboard-driven executor path |
| SY07 | Screenshot | take a screenshot | 🟡 | deterministic screenshot routing exists and Phase 3A safe host smoke now verifies the saved screenshot path |
| SY08 | Lock screen | lock screen | 🟡 | exact and natural lock-screen phrasing now route through the existing executor action |
| SY09 | Sleep Mac | put Mac to sleep | 🟡 | exact and natural sleep phrasing now route through the existing executor action |
| SY10 | Empty trash | empty trash | ❌ | not built |
| SY11 | Show desktop | show desktop | 🟡 | exact and natural show-desktop phrasing now route through the existing executor action |
| SY12 | Mission Control | show all windows | ❌ | not built |
| SY13 | Switch app | switch to Cursor | ✅ | working |
| SY14 | Minimize window | minimize this | 🟡 | verification is still unreliable |
| SY15 | Quit app | quit Chrome | ✅ | working |
| SY16 | Force quit | force quit | ❌ | not built |
| SY17 | Check battery | how much battery | 🟡 | deterministic battery queries now route through `pmset` and are covered by the Phase 3A safe host smoke |
| SY18 | Check WiFi | am I on wifi | 🟡 | deterministic Wi-Fi queries now route through `networksetup` and are covered by the Phase 3A safe host smoke |
| SY19 | Dark mode toggle | enable dark mode | 🟡 | deterministic dark-mode on or off phrases now route through the existing appearance-toggle action |
| SY20 | Do not disturb | turn on DND | 🟡 | deterministic DND on or off phrases now route through the existing Control Center automation path |

### Terminal and Code

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| T01 | Open Terminal | open terminal | ✅ | host smoke verified; plain `open terminal` now opens a fresh Terminal window instead of only focusing an existing one |
| T02 | Run command | run git status | ✅ | allowlist works |
| T03 | Open project in Terminal | open mac-butler in terminal | ✅ | working |
| T04 | Open in Claude Code | open adpilot in claude code | 🟡 | deterministic project-open routing now preserves the Claude Code editor hint and launches it through a fresh Terminal window; broader host verification is still thin |
| T05 | Open in Codex | open adpilot in codex | 🟡 | deterministic project-open routing now preserves the Codex editor hint and launches it through a fresh Terminal window; broader host verification is still thin |
| T06 | Open in Cursor | open adpilot in cursor | 🟡 | project-open routing already respects explicit Cursor hints on the covered path; broader host verification is still thinner than VS Code |
| T07 | Open in VS Code | open adpilot in vscode | ✅ | working |
| T08 | Run tests | run tests for mac-butler | 🟡 | deterministic `run tests` routing now resolves the current workspace or named project, infers a local test command, and executes it on the typed executor path; richer target selection and result verification are still limited |
| T09 | Git status | show git status | ✅ | working |
| T10 | Git commit | commit with message X | 🟡 | confirmation-aware typed git commit flow is now wired on the executor path; host verification remains command-exit based |
| T11 | Git push | push to main | 🟡 | confirmation-aware typed git push and commit-and-push flows are now wired on the executor path; host verification remains command-exit based |
| T12 | Ask Claude Code to fix | fix login bug in adpilot | ❌ | not wired |
| T13 | SSH to VPS | connect to VPS | 🟡 + 🔧 | deterministic SSH-open routing now uses the configured default host and opens a real Terminal-backed helper flow; host credentials and reachability still gate success |
| T14 | Check VPS status | check my VPS | 🟡 + 🔧 | typed VPS status now uses the configured default host and returns truthful setup or connection failures instead of generic empty degradation |

### Calendar and Tasks

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| C01 | Read today calendar | what's on my calendar | 🔧 | `calendar_read` supports today, tomorrow, and this-week reads with spoken summaries; live reads still require Calendar automation access |
| C02 | Read next event | what's my next meeting | 🔧 | `calendar_read` supports next and upcoming meeting reads with spoken summaries; live reads still require Calendar automation access |
| C03 | Add calendar event | add meeting tomorrow 3pm | 🟡 | inline natural-time phrases now route deterministically through router/executor without calendar-name clarification; hosts without Calendar automation access still fail truthfully and are skipped in Phase 3A host smoke |
| C04 | Set reminder | remind me at 5pm to call vedang | 🟡 | reminders now verify against the Reminders list when automation access is available and fail truthfully when Reminders automation is unavailable |
| C05 | Read tasks | what are my tasks | ✅ | deterministic task-read route is in place |
| C06 | Add task | add task fix login bug | ✅ | natural-language task add route is in place |
| C07 | Mark task done | mark login bug as done | ❌ | task-done flow still needs a verified completion path |
| C08 | Read Obsidian notes | open my notes | ❌ + 🔧 | vault path is not configured and the read flow is still thin |
| C09 | Add Obsidian note | add note fix login bug | 🟡 | note writes now use vault-relative Obsidian open URLs and avoid duplicate daily-date filenames; broader note-add phrasing is still thin |
| C10 | Search Obsidian | find notes about adpilot | ❌ | not built |

### Search and Knowledge

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| K01 | Web search | search X | 🟡 | search uses SearXNG first and falls back through DuckDuckGo and Exa when available, now with repeated-query caching and snippet-first live fetches; quality still depends on backend reachability |
| K02 | Latest news | latest news | 🟡 | current-news latency now benefits from repeated-query caching, snippet-first fetches, and a typed real-task benchmark path, but backend reachability still affects quality |
| K03 | News on topic | latest news on claude mythos | 🟡 | `agents/runner.py` now hardens current-news lookups with Google News RSS fallback plus repeated-query caching and snippet-first enrichment when search snippets are already rich |
| K04 | Weather | what's the weather in mumbai | 🟡 | dedicated `wttr.in` lookup with Open-Meteo fallback is now live and regression-covered on current plus tomorrow phrasing; quality still depends on public-provider reachability |
| K05 | Quick fact | who is president of america | 🟡 | direct DuckDuckGo instant-answer and Wikipedia summary lookup now run before generic search fallback; current-role variants like `who is PM of India` skip lightweight model narration and go to retrieval-backed lookup |
| K06 | Summarize page | summarize this article | 🟡 | current page summarization and fetch reuse indexed page snapshots first, then fall back to Jina and direct HTML extraction when needed |
| K07 | Summarize YouTube | summarize this video | 🟡 | current video summarization now falls back through captions, transcript APIs, `yt-dlp`, Whisper, and page extraction |
| K08 | Research topic | research X deeply | 🟡 | deep research now fast-paths live news, page-read, search, and project-status shaped questions into the typed retrieval agents first; broader multi-step research is still slower than hot lookup paths |
| K09 | Project status | how is adpilot doing | 🟡 | `lookup_project_status` now summarizes tracked project state, blockers, next tasks, health, and GitHub repo status when available |
| K10 | GitHub status | any issues on adpilot | 🟡 | tracked-project and direct `owner/repo` GitHub status now work through public API reads; token still improves private-repo access and rate limits |

### Vision and Screen

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| V01 | Take screenshot | take a screenshot | 🟡 | screenshot support exists, but routing is still incomplete |
| V02 | Read screen | what is on my screen | ❌ | vision path is not wired |
| V03 | Describe window | what am I looking at | ❌ | no real vision pipeline yet |
| V04 | Read image text | read this image | ❌ | OCR path is not wired |
| V05 | Understand image | what is in this image | ❌ + 🔧 | local vision model setup is still missing |
| V06 | Click on screen | click the blue button | ❌ | needs stable vision plus GUI control |
| V07 | Fill form | fill this form | ❌ | needs stable vision plus GUI control |
| V08 | Read PDF on screen | read this PDF | ❌ | not built |

### Conversation and Intelligence

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| I01 | Session memory | "with subject hello" after email | ✅ | email follow-up fields and recent turns now persist across short restarts through the `session_context.py` snapshot |
| I02 | Multi-turn commands | two-part commands connected | ✅ | pending dialogue resolution is wired, regression-covered, and restored truthfully after short restarts |
| I03 | Startup briefing | GitHub weather tasks on wake | 🟡 | startup briefing is trigger-gated with deterministic fallback; the weather line now uses a speech-safe provider format, default `butler.py` startup stays passive until clap, wake phrase, or explicit command, and `--clap-only` keeps spoken wake disabled |
| I04 | Mood-aware responses | 3am tone vs morning tone | ❌ | mood-aware reply shaping is still too shallow to count as complete |
| I05 | Brainstorm mode | "lets think about adpilot" | 🟡 | general conversation lane exists, but not a dedicated high-opinion brainstorm subsystem |
| I06 | Argue back | "you should work on email-infra" | ❌ | no explicit opinion or pushback lane |
| I07 | Yesterday memory | "like we discussed" | 🟡 | partial only |
| I08 | Deep project knowledge | "how is adpilot doing" | 🟡 | partial |
| I09 | Proactive suggestions | "you haven't committed in 3 days" | ❌ | heartbeat logic is not smart enough yet |
| I10 | Natural language anything | say anything and it understands | 🟡 | question lane is better, but live quality is still RAM-sensitive |

### HUD Frontend

| ID | Capability | Voice example | Effective status | Current gap or note |
| --- | --- | --- | --- | --- |
| H01 | Live WebSocket events |  | ✅ | working |
| H02 | Shows current intent |  | ✅ | working |
| H03 | Shows last heard |  | ✅ | working |
| H04 | Shows last response |  | ✅ | working |
| H05 | Shows active tool |  | ✅ | working |
| H06 | Shows tool result |  | ✅ | working |
| H07 | Agent thinking trace |  | ✅ | working |
| H08 | Plan steps live |  | ✅ | working |
| H09 | Rolling log 100 events |  | 🟡 | event feed still truncates too aggressively |
| H10 | Shows memory being read |  | ✅ | memory-read event publishing is wired |
| H11 | Shows which model running |  | 🟡 | speech/runtime chips now report NVIDIA Riva backends truthfully, but per-command model visibility is still partial |
| H12 | Shows session context/pending |  | 🟡 | pending events publish correctly; HUD rendering is still basic |
| H13 | Shows mood state |  | 🟡 | mood events publish through runtime telemetry; front-end depth remains limited |
| H14 | Project graph |  | ✅ | working |
| H15 | SearXNG status |  | ✅ | shows offline state truthfully |
| H16 | VPS status |  | ✅ | shows unreachable state truthfully |
| H17 | Offline banner |  | ✅ | working |
| H18 | Download logs |  | ❌ | not built |
| H19 | Filter logs by type |  | ❌ | not built |
| H20 | Timing per command |  | ❌ | not built |

## Genuinely Impossible or Unsupported Without a Different Integration

- Instagram DM read or post without an approved external API path
- WhatsApp message history read through a clean supported API on the local-app path
- iMessage read access to other people's messages through a safe supported API
- Any action that requires root or SIP bypass

## Needs Your Setup

| Setup requirement | Unlocks or improves |
| --- | --- |
| `bash scripts/start_searxng.sh` | improves K01, K02, K03, and K08 search and research quality |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | improves K10 for private repos and higher rate limits, and improves I08 project-context quality |
| `NVIDIA_API_KEY` plus NVIDIA Riva Python clients | unlocks provider-primary LLM, TTS, and STT paths |
| `DEEPSEEK_API_KEY` | unlocks optional DeepSeek V4 Flash/Pro evaluation on the generic OpenAI-compatible provider path |
| `MOONSHOT_API_KEY` | unlocks optional Kimi K2.6 evaluation on the generic OpenAI-compatible provider path |
| `VPS` credentials in `butler_secrets` | unlocks T13 and T14 |
| `pip install pywhatkit pyautogui` | improves W02, W03, W05, W06, W07 and GUI-heavy flows |
| `ollama pull llama3.2-vision` | unlocks V02-V05 and the vision stack baseline |
| `OBSIDIAN_VAULT_PATH` in `butler_config.py` | unlocks C08-C10 and improves M10 |

## Wiring Plan by Domain

| Workstream | Primary owners | Capability IDs | What needs wiring next |
| --- | --- | --- | --- |
| Browser and page actions | `intents/router.py`, `pipeline/router.py`, `executor/engine.py`, `agents/browser_agent.py` | B01-B20 | tab/window/back/refresh host smoke is now in place; next gaps are incognito, YouTube-specific search/play hardening, and page-read/page-summary verification beyond URL state |
| Filesystem and Finder | `intents/router.py`, `executor/engine.py`, `capabilities/registry.py` | F01-F18 | common local path routing plus create/open/read/write/find/list/move/copy/rename/delete/zip flows are now landed; next gaps are broader naming variants, terminal-created files, and the Google Doc/Sheet create-new shortcuts |
| Email and WhatsApp | `brain/session_context.py`, `intents/router.py`, `executor/engine.py`, `channels/*` when needed | E01-E08, W01-W07 | Gmail attachment drafts plus WhatsApp file-share assist are now truthful on the covered path; the next gaps are inbox/reply reads, richer chat targeting, and true delivery/file-send verification beyond manual confirmation |
| Calendar, reminders, tasks, and notes | `intents/router.py`, `executor/engine.py`, `skills/calendar_skill.py`, `context/obsidian_context.py` | C01-C10 | calendar and reminder verification are now truthful on supported hosts; next gaps are task-done wiring plus Obsidian search/read flows, while Calendar read/write remain setup-dependent on host automation access |
| Current info and research | `agents/runner.py`, `agents/research_agent.py`, `capabilities/registry.py`, `brain/tools_registry.py` | K01-K10, B10, B16, M09, K07 | indexed page retrieval plus dedicated weather, quick-fact, GitHub-status, project-status, and current-page lookup are now in place; those retrieval roles now stay NVIDIA-first in the default chain, news rejects timeout filler, deeper research fast-paths live retrieval first, and `scripts/benchmark_models.py --real-tasks` covers quick-fact, weather, GitHub, project-status, page-read, and news probes |
| System control | `intents/router.py`, `executor/engine.py` | SY01-SY20 | deterministic volume, mute, brightness, screenshot, lock-screen, sleep, show-desktop, battery, wifi, dark-mode, and DND routing are now wired; safe host smoke is in place and the next gaps are disruptive-control smoke plus empty-trash, mission-control, and force-quit |
| Terminal, editors, and project actions | `projects/open_project.py`, `executor/engine.py`, `capabilities/planner.py` | T01-T14 | plain Terminal opens now create a fresh window, explicit editor hints for Claude/Codex/Cursor/VS Code now survive project-open routing, `run tests` resolves workspace-local commands, and git/VPS flows are typed plus confirmation-aware on the covered path; next gaps are ask-Claude fix workflows, richer test-target selection, and deeper host verification |
| Vision and full computer control | `agents/vision.py`, `executor/engine.py`, `agents/browser_agent.py` | V01-V08, B11-B12, V06-V07 | treat screenshot capture, OCR, screen understanding, click targeting, and form fill as one stack: capture -> detect -> act -> verify; do not wire click/fill until the vision read path is stable |
| Conversation, memory, and proactive behavior | `brain/session_context.py`, `brain/conversation.py`, `brain/mood_engine.py`, `daemon/heartbeat.py`, `memory/*` | I01-I10 | recent-turn and pending-memory persistence now live in `session_context.py`; next gaps are brainstorm, mood, yesterday memory, and proactive suggestions as explicit tested flows |
| HUD and telemetry | `runtime/telemetry.py`, `projects/dashboard.py`, `projects/frontend/modules/*` | H01-H20 | localhost dashboard defaults to `7532` with native/browser auto-open opt-in only; project cards now use enriched project-store data and live-focus highlighting, recent Notification Center activity now surfaces in the runtime notifications panel, and the next gaps are pending-state depth, richer mood display, log download/filtering, and per-command timing on the existing WS envelope |

## Suggested Phase Sequence From Here

| Slice | Main scope | Why this order |
| --- | --- | --- |
| Phase 3B — knowledge and retrieval breadth | weather/fact/news latency, GitHub status, page/article/video summarization reliability, indexed retrieval | complete for the current advertised surface: page-read and project-status now have typed retrieval paths, deeper research fast-paths live lookups first, and the real-task benchmark path covers the main retrieval routes |
| Phase 3C — messaging and project tooling | Gmail attachments, WhatsApp compose/send refinement, git confirmations, VPS checks | complete for the current advertised surface: attachment-aware compose, WhatsApp file-share assist, git confirmations, run-tests, explicit editor-openers, and truthful VPS default-host degradation are all wired on the existing owners |
| Phase 3D — HUD visibility and proactive loops | pending context UI, mood UI, logs/timing, smarter heartbeat suggestions | now the primary remaining feature slice; the runtime already publishes most of the signals, but the HUD still needs deeper pending/mood/log/timing exposure |
| Phase 4 — vision and full GUI control | screen reading, OCR, click/fill, PDF-on-screen, browser form control | this stack is heavier, setup-sensitive, and should land only after the deterministic action surface is reliable |
