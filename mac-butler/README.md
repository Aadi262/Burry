# Mac Butler

Mac Butler is a local operator agent for macOS. It gathers context from your work machine, asks a local Ollama model for a JSON action plan, safely executes what makes sense, speaks the response aloud, then waits a few seconds for a follow-up.

Everything runs locally. No API keys. No cloud round-trips.

## Features

- Context gathering from git activity, Cursor or VS Code history, TODOs, Obsidian notes, and optional VPS checks
- Two-stage local operator planning with Ollama: planner JSON first, spoken reply second
- Safe execution engine for app launches, folder opens, command runs, notes, notifications, reminders, URLs, and SSH actions
- Specialist agents for news, search, VPS inspection, memory compression, code generation, GitHub MCP calls, and bug finding
- Optional Brave Search MCP and GitHub MCP integration
- Background heartbeat and bug-hunter daemons for quiet monitoring
- Local neural TTS with Kokoro on Apple Silicon, plus safe macOS `say` fallback
- Keyboard trigger and clap trigger support
- Short post-briefing follow-up window using text input for now

## Prerequisites

- macOS
- Python 3.11+
- Ollama installed and running
- Optional: Spotify desktop app for music actions
- Optional: passwordless SSH keys for VPS commands

## Quick Start

```bash
cd mac-butler
chmod +x setup.sh
./setup.sh
source venv/bin/activate
bash scripts/start_searxng.sh
python trigger.py
```

Press `Cmd+Shift+B` to trigger Butler, or run `python trigger.py --clap` for clap mode.

Start the local search backend with `bash scripts/start_searxng.sh`.

## Configuration

Edit `butler_config.py` before using operator features:

```python
OBSIDIAN_VAULT_NAME = "YourVaultName"
DEVELOPER_PATH = "~/Developer"
VPS_HOSTS = []
OLLAMA_MODEL = "qwen2.5:14b"
OLLAMA_FALLBACK = None
SPOTIFY_ENABLED = True
TTS_ENGINE = "kokoro"
TTS_VOICE = "af_bella"
TTS_SPEED = 1.0
PIPER_MODEL_PATH = ""
```

### Obsidian Vault

Set `OBSIDIAN_VAULT_NAME` to the folder name inside:

```text
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/
```

If the vault name is left as `YourVaultName`, Butler skips Obsidian context and rejects Obsidian write actions.

### VPS Hosts

Add entries like this to `VPS_HOSTS`:

```python
VPS_HOSTS = [
    {"label": "Main VPS", "host": "root@1.2.3.4"},
    {"label": "Worker", "host": "ubuntu@5.6.7.8"},
]
```

The VPS context only does a quick reachability check. SSH actions assume key-based auth is already configured.

### MCP Servers

Brave Search MCP and GitHub MCP are optional. Configure them in `butler_config.py` and `secrets/local_secrets.json`.

Example local secrets:

```json
{
  "mcp": {
    "brave": {
      "enabled": true,
      "env": {
        "BRAVE_API_KEY": "..."
      }
    },
    "github": {
      "enabled": true,
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "..."
      }
    }
  }
}
```

## What Butler Can Do

Example interactions:

- "Open the repo I was in and start the dev server."
- "Write this idea into Obsidian and remind me in 30 minutes."
- "Check whether the VPS is up."
- "Just brief me, don't open anything."

If Butler only needs to brief you, the model returns `actions: []` and nothing is executed.

## Action Types

Full action reference:

```json
{"type": "open_app", "app": "Cursor"}
{"type": "open_app", "app": "Spotify"}
{"type": "open_app", "app": "Claude"}
{"type": "open_app", "app": "Terminal"}
{"type": "open_folder", "path": "~/Developer/project-name"}
{"type": "run_command", "cmd": "npm run dev", "cwd": "~/Developer/project-name"}
{"type": "run_command", "cmd": "git status", "cwd": "~/Developer/project-name"}
{"type": "play_music", "mode": "focus|chill|hype|off"}
{"type": "write_file", "path": "~/Developer/notes.md", "content": "...", "mode": "append|overwrite"}
{"type": "create_folder", "path": "~/Developer/new-project"}
{"type": "obsidian_note", "title": "Note title", "content": "...", "folder": "Daily|Projects|Ideas"}
{"type": "ssh_open", "host": "user@ip", "label": "VPS name"}
{"type": "ssh_command", "host": "user@ip", "cmd": "systemctl status nginx"}
{"type": "open_url", "url": "https://..."}
{"type": "notify", "title": "Butler", "message": "..."}
{"type": "remind_in", "minutes": 30, "message": "Check campaign stats"}
{"type": "run_agent", "agent": "news", "topic": "AI news last 24h"}
{"type": "run_agent", "agent": "search", "query": "what is X"}
{"type": "run_agent", "agent": "vps", "host": "root@1.2.3.4"}
{"type": "run_agent", "agent": "github", "tool": "list_pull_requests", "arguments": {"owner": "...", "repo": "..."}}
{"type": "run_agent", "agent": "bugfinder", "target": "~/Burry/mac-butler", "scope": "quick"}
```

## Test Sequence

Run the operator upgrade checks in this order:

```bash
source venv/bin/activate
python scripts/system_check.py
python scripts/system_check.py --live
python daemon/bug_hunter.py
```

`python scripts/system_check.py` covers unit tests, specialist agents, executor agent dispatch, confirmation gate, heartbeat, and `butler.py --test`.

`python scripts/system_check.py --live` adds a full voice run.

`python daemon/bug_hunter.py` runs the background bug-finder once.

## Project Structure

```text
mac-butler/
├── butler.py
├── butler_config.py
├── trigger.py
├── brain/
│   └── ollama_client.py
├── context/
│   ├── __init__.py
│   ├── git_context.py
│   ├── obsidian_context.py
│   ├── tasks_context.py
│   ├── vscode_context.py
│   └── vps_context.py
├── executor/
│   ├── __init__.py
│   └── engine.py
├── voice/
│   └── tts.py
└── daemon/
    ├── clap_detector.py
    └── com.mac.butler.plist
```

## Permissions

For keyboard mode, grant Accessibility permissions to your terminal app.

For clap mode, grant Microphone permissions to the terminal app running Butler.

## Notes

- Spotify URI playback only works if Spotify desktop is installed.
- Obsidian actions need a real vault name in `butler_config.py`.
- `run_command` is intentionally allowlisted and runs without shell operators.
- File writes are restricted to safe project roots instead of writing arbitrary paths from model output.
