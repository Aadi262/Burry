# Mac Butler Requirements Capture

This file captures the architecture and behavior targets that were requested across the recent prompt chain, so implementation can be checked against one source of truth instead of scattered chat history.

## 1. Core Runtime

- Passive Mac activity watcher that records frontmost app, open windows, workspace, Spotify track, and browser URL.
- Deterministic router for common commands so Spotify, app control, folders, reminders, notes, and VPS checks do not hit the LLM.
- Fast STT on Apple Silicon with `mlx-whisper` first and a usable fallback path.
- Clean command pipeline: `STT -> router -> executor OR LLM -> TTS`.

## 2. Two-Stage Brain

- Planner stage should decide current focus, next action, and optional actions as JSON.
- Speech stage should turn that plan into sharp Butler-style spoken output.
- Prompt context should stay compressed and carry identity, tasks, memory, and current Mac activity.
- Startup briefing and "what next" flows should use this brain instead of ad hoc one-shot prompts.

## 3. Memory And Tasks

- Persistent task store in `tasks/tasks.json`.
- Layered memory:
  - Layer 1: small always-loaded index
  - Layer 2: project detail notes
  - Layer 3: session archive/search
- Session updates should feed both classic memory and layered memory.

## 4. Multi-Agent System

- Specialist agents for news, VPS, search, code, GitHub, and bug finding.
- Orchestrator should emit `run_agent` actions when the request or context calls for them.
- Agent results should be fed back into final speech so the user hears synthesized outcomes, not raw tool noise.

## 5. Safety And Background Loops

- Confirmation gate for dangerous actions like `git push`, destructive Docker commands, SSH mutations, and overwrite writes.
- KAIROS-style heartbeat for safe proactive nudges only.
- `open_last_workspace` should use Mac activity state first, then memory fallback.

## 6. Experience Quality

- Voice should avoid repetitive canned lines.
- Replies should stay aligned to actual work context: `mac-butler`, `email-infra`, current workspace, current tasks.
- Unknown commands should ask for clarification instead of drifting into generic project monologues.
- Deterministic actions should execute with workspace-aware context.

## Current Focus For Implementation

- Make the live runtime actually use the two-stage brain and agent system where intended.
- Keep deterministic commands fast and direct.
- Prevent "architecture exists on disk but not in runtime" drift.
