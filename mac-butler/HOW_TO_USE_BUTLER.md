# How To Use Mac Butler

This is the quickest way to run Butler on this Mac without guessing.

## What Is Running

- Model: `qwen2.5-coder:14b`
- Obsidian vault: `Burry`
- VPS: `root@194.163.146.149`
- Voice output: enabled through macOS `say`
- Voice follow-up: short microphone clips transcribed through `SpeechRecognition`
- Typed follow-up: still works in terminal as fallback

Important:
- Butler can speak to you.
- Butler can now try to hear a short spoken follow-up after the response.
- After Butler speaks, there is a 4-second microphone follow-up window.
- If transcription fails, type in the same terminal as fallback.

## One-Time Setup

From the project root:

```bash
cd /Users/adityatiwari/Burry/mac-butler
source venv/bin/activate
```

## Run Butler Once

This runs one full cycle with voice and actions:

```bash
venv/bin/python butler.py
```

What happens:
- Butler gathers context from git, tasks, memory, Obsidian, and VPS state
- Qwen generates a JSON plan
- Butler executes actions
- Butler speaks aloud
- Butler listens for a short spoken follow-up, then falls back to typed input

## Test Mode

This prints the plan without speaking or executing:

```bash
venv/bin/python butler.py --test
```

Use this when you want to inspect the response safely.

## Start Clap Mode

This keeps Butler listening for the double-clap trigger:

```bash
venv/bin/python trigger.py --clap
```

When clap mode is active:
- double-clap to trigger Butler
- Butler will speak aloud
- speak a short follow-up during the wait window
- if transcription misses it, type into that same terminal

## Start Keyboard Mode

```bash
venv/bin/python trigger.py
```

Shortcut:
- `Cmd + Shift + B`

## Start Both Keyboard And Clap

```bash
venv/bin/python trigger.py --both
```

Or double-click:

```bash
run_live.command
```

## How To Stop Clap Mode

If it is running in the current terminal:
- press `Ctrl + C`

If it is running somewhere else:

```bash
ps -ef | rg "trigger.py --clap"
kill <PID>
```

If you started `--both`, look for `trigger.py --both` instead.

Double-click `run_clap.command` if you want a clap-only launcher.

## How To Check Butler Memory

```bash
venv/bin/python memory/store.py
```

This shows:
- last active session
- recent Butler responses
- remembered commands
- learned patterns

## How To Check Obsidian Context

```bash
venv/bin/python context/obsidian_context.py
```

This confirms Butler is reading from the `Burry` vault.

## How To Check VPS Context

```bash
venv/bin/python context/vps_context.py
```

This confirms:
- whether the VPS is reachable
- whether a local secret is saved

## VPS Commands To Reuse

These use the saved VPS host and password from `secrets/local_secrets.json`.

```bash
python3 scripts/vps.py status
python3 scripts/vps.py exec "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
python3 scripts/vps.py exec "systemctl status ollama-server --no-pager"
python3 scripts/vps.py shell
```

Step by step for Ollama offloading:
1. SSH into the VPS or run `python3 scripts/vps.py shell`.
2. Run `OLLAMA_BASIC_AUTH_PASS='<password>' bash scripts/setup_vps_ollama.sh` on the VPS.
3. Set `USE_VPS_OLLAMA = True` and `VPS_OLLAMA_URL = 'http://194.163.146.149:8765/ollama'` in `butler_config.py`.
4. Save the auth password under `ollama` in `secrets/local_secrets.json`.
5. Run `venv/bin/python -c "from brain.ollama_client import check_vps_connection; print(check_vps_connection())"`.

## How To Check The Model

```bash
curl -sS http://127.0.0.1:11434/api/tags
```

Look for:
- `qwen2.5-coder:14b`

## Current Limitation

Right now Butler is:
- clap-triggered or keyboard-triggered
- voice output enabled
- short microphone follow-up enabled
- typed fallback still present

What is still not built yet:
- continuous full-duplex conversation
- long-form always-listening assistant mode

So the current real interaction loop is:
1. Trigger Butler with clap or keyboard
2. Listen to Butler speak
3. Speak a short follow-up
4. Type in the terminal only if the transcript misses

## Best Commands

Use these most often:

```bash
venv/bin/python butler.py --test
venv/bin/python butler.py
venv/bin/python trigger.py --clap
venv/bin/python trigger.py --both
```
