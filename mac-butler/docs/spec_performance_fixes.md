# Performance Fixes Spec

Source note: reconstructed from the user-provided prompt chain because the original referenced document index was not locally accessible during the audit.

## Scope

Upgrade Mac Butler at `/Users/adityatiwari/Burry/mac-butler`.

Two things to do in order:

1. Apply the performance fixes: prompt compression, two-stage LLM, few-shot examples.
2. Add the Claude Code-style harness patterns: observe loop, task system, layered memory.

## Part A: Performance Fixes

### A1: Rewrite `brain/ollama_client.py`

- Use a two-stage LLM caller with compressed prompts and few-shot examples.
- Stage 1: planning, low temperature, decisive JSON output.
- Stage 2: speech, natural Butler-style speech.
- Include identity and memory in the speech stage.
- Add robust JSON stripping and fallback handling.

### A2: Add `get_last_session_summary` to `memory/store.py`

- Returns a 3-line max summary of the last session.
- Includes timestamp, a short action summary, and a clipped speech summary.

### A3: Add context compression to `context/__init__.py`

- Add `_compress(raw, limit=500)`.
- Remove noise and raw git hashes.
- Final context block should stay compact and high-signal.

## Part B: Claude Code Harness Patterns

### B1: `tasks/task_store.py`

- Persistent task system inspired by `TodoWrite`.
- Supports seeding, listing, syncing from `TODO.md`, filtering active tasks.

### B2: `tasks/__init__.py`

- Export task-store helpers.

### B3: `memory/layered.py`

- Three-layer memory:
  - Layer 1: `MEMORY.md`
  - Layer 2: project detail files
  - Layer 3: session JSONL archives

### B4: Observe loop in `butler.py`

- After execution, feed results back into the model.
- Short follow-up sentence only when results have meaningful output.

### B5: Wire tasks into `context/__init__.py`

- Sync from `TODO.md` on context build.
- Include task list in prompt context.

### B6: Wire layered memory into `context/__init__.py`

- Add memory index to the top of context.

### B7: Save to layered memory after each session

- Save session summary.
- Update project detail notes.
- Append short index entries.

## Expected Outcome

- Context under roughly 600 chars with tasks and memory included.
- Two-stage LLM outputs specific Butler speech, not generic filler.
- Sessions persist into both classic memory and layered memory.
