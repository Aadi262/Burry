# Butler Status

Last updated: 2026-04-04

## Purpose

Mac Butler is a local operator agent for Aditya's Mac.
It wakes on clap or keyboard, gathers work context, asks a local Ollama model what matters now, executes safe actions, speaks the reply, and waits for a short follow-up.

## What Is Done

- Butler identity layer is in place for Aditya, his projects, tone, and working style.
- Two-stage Ollama planning is in place:
  - stage 1 decides focus, next step, and actions
  - stage 2 writes the spoken reply
- Observe loop is wired so execution results can rewrite the final speech.
- Structured context is compressed before sending to the model.
- Persistent memory is in place:
  - recent sessions
  - learned commands
  - project state
  - layered memory index and session archive
- Task system is in place with persistent task storage.
- Specialist agents are in place for:
  - news
  - search
  - VPS inspection
  - memory compression
  - code generation
  - GitHub MCP calls
  - bug finding
- Optional MCP support is in place for:
  - Brave Search
  - GitHub
- Background daemons are in place for:
  - KAIROS heartbeat
  - bug hunter
- Safe executor is in place for:
  - apps
  - folders
  - commands
  - Spotify
  - Obsidian notes
  - notifications
  - reminders
  - SSH actions
- Obsidian vault is configured to `Burry`.
- VPS context is configured for `root@194.163.146.149`.
- Butler no longer silently falls back to a smaller Ollama model.
- Butler no longer keeps reopening the editor on follow-up turns.
- Startup behavior now prefers:
  - playing music
  - respecting the current open workspace
  - not reopening editor windows if one is already running

## Current Voice State

- Current TTS backend: local macOS voice
- Current selected voice: `Flo (English (US))`
- Current speech shaping improvements:
  - phonetic handling for `Aditya Tiwari`
  - tighter sentence length
  - natural pause markers
  - better cleanup of technical text before speaking
- Piper-ready hook exists in config and TTS code, but Piper is not installed yet.

## Current Runtime Config

- Model: `qwen2.5-coder:14b`
- Obsidian vault: `Burry`
- Spotify auto-play: enabled
- Voice follow-up: enabled
- Trigger modes:
  - `trigger.py --clap`
  - `trigger.py`
  - `trigger.py --both`
- One-click launchers:
  - `run_clap.command`
  - `run_live.command`

## How The System Works

1. Trigger wakes Butler.
2. Butler gathers compressed context from:
   - layered memory
   - task list
   - editor/workspace context
   - Obsidian
   - VPS reachability
   - time of day
3. Qwen stage 1 decides:
   - what Aditya is focused on
   - the single next step
   - safe actions
4. Qwen stage 2 writes the spoken JSON reply.
5. Butler aligns actions with the real machine state.
6. Executor runs safe actions.
7. Butler speaks the result.
8. Butler records session memory and waits for a follow-up.

## Codebase Map

- `butler.py`
  - main agent loop
  - action alignment
  - follow-up wait
  - memory writes
- `brain/ollama_client.py`
  - two-stage LLM call
  - compact prompts
  - JSON handling
- `context/`
  - gathers compressed context for the model
- `executor/engine.py`
  - safe action execution
- `voice/tts.py`
  - local speech output
  - pronunciation shaping
  - Piper-ready backend hook
- `voice/stt.py`
  - microphone follow-up capture
- `memory/store.py`
  - persistent session memory
- `memory/layered.py`
  - memory index, project notes, session archive
- `tasks/task_store.py`
  - persistent task list
- `identity/profile.yaml`
  - Aditya identity and project registry
- `trigger.py`
  - clap and keyboard trigger entrypoint
- `daemon/com.mac.butler.plist`
  - login-time clap LaunchAgent template

## Latest Verified Checks

- `venv/bin/python tasks/task_store.py` passed
- `venv/bin/python memory/layered.py` passed
- `venv/bin/python -m unittest discover -s tests` passed
- `venv/bin/python scripts/system_check.py` passed
- `venv/bin/python scripts/system_check.py --live` passed
- `venv/bin/python daemon/bug_hunter.py` reported no failures

## Known Gaps

- Butler still uses macOS TTS by default, not a true neural local TTS yet.
- Voice follow-up is still weaker than the main TTS path.
- Detached background startup for `--both` is unreliable in a headless shell; a real Terminal window works better.
- Continuous always-listening full-duplex mode is not built yet.

## What Should Happen Next

1. Configure Brave MCP and GitHub MCP secrets if you want live web and repo awareness.
2. Install and wire a real local neural TTS backend, ideally Piper.
3. Upgrade live STT to a stronger local path.
4. Tighten current-workspace detection so Butler always opens the right project only when needed.

## Best Way To Run Right Now

For a real live session:

```bash
cd /Users/adityatiwari/Burry/mac-butler
venv/bin/python -u trigger.py --both
```

Or double-click:

- `run_live.command`
- `run_clap.command`
