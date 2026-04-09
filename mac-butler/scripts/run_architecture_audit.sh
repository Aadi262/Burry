#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +"%Y-%m-%dT%H-%M-%S")"
GENERATED_AT="$(venv/bin/python -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat())')"
OUT_DIR="$ROOT/docs/audits/reports"
REPORT="$OUT_DIR/architecture-audit-$STAMP.md"
LATEST="$OUT_DIR/latest.md"

mkdir -p "$OUT_DIR"

TARGET_TESTS=(
  tests/test_architecture_phase2.py
  tests/test_instant_lane.py
  tests/test_background_lane.py
  tests/test_intent_router.py
  tests/test_dashboard.py
  tests/test_ollama_client.py
  tests/test_executor.py
  tests/test_runtime_telemetry.py
  tests/test_remaining_items.py
  tests/test_project_store.py
)

{
  echo "# Mac Butler Architecture Audit"
  echo
  echo "Generated: $GENERATED_AT"
  echo
  echo "## Working Tree"
  echo
  echo '```bash'
  git status --short
  echo '```'
  echo
  echo "## Ollama Models"
  echo
  echo '```bash'
  if command -v ollama >/dev/null 2>&1; then
    ollama list || true
  else
    echo "ollama CLI not found"
  fi
  echo '```'
  echo
  echo "## Effective Routed Models"
  echo
  echo '```text'
  venv/bin/python - <<'PY'
from brain.ollama_client import pick_agent_model, pick_butler_model

butler_roles = ["voice", "planning", "vision", "review", "coding"]
agent_roles = [
    "news",
    "market",
    "hackernews",
    "reddit",
    "github_trending",
    "vps",
    "memory",
    "code",
    "search",
    "github",
    "bugfinder",
]

print("BUTLER")
for role in butler_roles:
    print(f"{role} -> {pick_butler_model(role)}")

print("\nAGENTS")
for role in agent_roles:
    print(f"{role} -> {pick_agent_model(role)}")
PY
  echo '```'
  echo
  echo "## Config Drift"
  echo
  echo '```text'
  venv/bin/python - <<'PY'
from butler_config import AGENT_MODEL_CHAINS, BUTLER_MODEL_CHAINS
from brain.ollama_client import _get_available_model_map

available = _get_available_model_map(force_refresh=True)
installed = sorted({name for name in available.values()})

configured = []
for chain in list(BUTLER_MODEL_CHAINS.values()) + list(AGENT_MODEL_CHAINS.values()):
    configured.extend(chain)
configured = sorted({name for name in configured if name})

missing = []
for model in configured:
    if model in available or model.split(":")[0] in available:
        continue
    missing.append(model)

print("INSTALLED")
for model in installed:
    print(model)

print("\nCONFIGURED_BUT_MISSING")
for model in missing:
    print(model)
PY
  echo '```'
  echo
  echo "## Targeted Regression Suite"
  echo
  echo '```bash'
  venv/bin/pytest "${TARGET_TESTS[@]}" -q
  echo '```'
  echo
  echo "## CLI Smoke"
  echo
  echo '```bash'
  venv/bin/python butler.py -c "how are you" --test
  venv/bin/python butler.py -c "latest AI news" --test
  venv/bin/python butler.py -c "stop" --test
  echo '```'
} > "$REPORT" 2>&1

cp "$REPORT" "$LATEST"
echo "Saved architecture audit report to $REPORT"
echo "Updated latest report at $LATEST"
