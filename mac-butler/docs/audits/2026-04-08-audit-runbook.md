# Mac Butler Architecture Audit Runbook

Last updated: 2026-04-08

## Purpose

Run a repeatable architectural audit before and after each remediation phase so the next session can compare latency, model routing, dashboard behavior, and regression status from a known baseline.

## Primary Artifact

- Generated report directory: `docs/audits/reports/`
- Main command: `scripts/run_architecture_audit.sh`

## Audit Inputs

- Runtime routing and lane logic: `butler.py`
- Model routing and fallbacks: `butler_config.py`, `brain/ollama_client.py`, `brain/agentscope_backbone.py`
- Agent execution and model churn: `agents/runner.py`
- Memory fragmentation and writes: `memory/store.py`, `memory/long_term.py`, `memory/layered.py`, `memory/knowledge_base.py`
- Dashboard and observability: `projects/dashboard.py`, `runtime/telemetry.py`, `runtime/tracing.py`

## Audit Sequence

### 1. Environment and Model Baseline

Run:

```bash
ollama list
venv/bin/python -c 'from brain.ollama_client import pick_butler_model,pick_agent_model; print("voice", pick_butler_model("voice")); print("planning", pick_butler_model("planning")); print("review", pick_butler_model("review")); print("news", pick_agent_model("news")); print("hackernews", pick_agent_model("hackernews"))'
```

Goal:

- Confirm installed local models.
- Confirm what Butler actually selects from the configured chains.
- Detect stale configured fallbacks before code edits.
- If `ollama list` crashes with MLX or macOS backtrace noise, keep the report and treat it as an environment issue, not a Butler routing failure.

### 2. Config Drift Audit

Review:

- `butler_config.py`
- `brain/agentscope_backbone.py`
- `README.md`
- `HOW_TO_USE_BUTLER.md`
- `BUTLER_STATUS.md`
- `setup.sh`

Goal:

- Find configured but missing models.
- Find installed but unused models.
- Find default code paths that bypass the installed-model picker.

### 3. Targeted Regression Gate

Run:

```bash
venv/bin/pytest \
  tests/test_architecture_phase2.py \
  tests/test_instant_lane.py \
  tests/test_background_lane.py \
  tests/test_intent_router.py \
  tests/test_dashboard.py \
  tests/test_ollama_client.py \
  tests/test_executor.py \
  tests/test_runtime_telemetry.py \
  tests/test_remaining_items.py \
  tests/test_project_store.py \
  -q
```

Goal:

- Keep the lane work green while the remediation phases land.
- Verify dashboard, telemetry, executor, and config-related behavior together.

### 4. CLI Smoke Pass

Run:

```bash
venv/bin/python butler.py -c "how are you" --test
venv/bin/python butler.py -c "latest AI news" --test
venv/bin/python butler.py -c "stop" --test
```

Goal:

- Verify a deterministic reply, a background-lane acknowledgment, and a hard-stop path in one pass.

### 5. Phase-Specific Checks

Run after each phase:

- Phase 2: compare hot-path latency and dashboard poll behavior.
- Phase 3: verify unknown and question utterances avoid AgentScope unless tools are needed.
- Phase 4: count file writes per command and memory recall quality.
- Phase 5: verify imports, CLI smoke, and lane tests after module extraction.
- Phase 6: confirm dashboard telemetry endpoints reflect live state and stale or offline conditions.

## Artifact Update Rules

After each completed phase:

1. Update `docs/phases/2026-04-08-architecture-remediation-roadmap.md`.
2. Update `docs/phases/2026-04-08-architecture-remediation-status.md`.
3. Update `docs/audits/2026-04-08-next-session-handoff.json`.
4. Update `memory/plan_notebook.json`.
5. Run `scripts/run_architecture_audit.sh` and save the new report.

## Definition of Done

The remediation work is ready for a broader manual test pass only when:

- the audit report is fresh,
- the targeted regression suite is green,
- the model inventory and routing output are internally consistent,
- the phase tracker and plan notebook point at the same next phase,
- and the latest report captures any remaining blockers explicitly.
