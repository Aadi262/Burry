#!/usr/bin/env python3
"""
daemon/bug_hunter.py
Background smoke checker that keeps hunting for regressions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from agents.runner import run_agent
from butler_config import BUG_HUNTER_ENABLED, BUG_HUNTER_INTERVAL_MINUTES, BUG_HUNTER_MODEL
from executor.engine import Executor
from runtime.notify import notify

ROOT = Path(__file__).resolve().parent.parent
SAFE_HOST_SMOKE_ARGS = (
    "--json",
    "--phase1-host",
    "--phase1-host-only",
    "--phase3a-host",
    "--phase3a-host-only",
)


def run_bug_hunt_once() -> dict:
    command = [
        str(ROOT / "venv" / "bin" / "python"),
        str(ROOT / "scripts" / "system_check.py"),
        *SAFE_HOST_SMOKE_ARGS,
    ]
    probe = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=240,
    )

    raw = (probe.stdout or "").strip() or "{}"
    try:
        summary = json.loads(raw)
    except Exception:
        summary = {
            "ok": False,
            "steps": [
                {
                    "name": "system_check",
                    "ok": False,
                    "output": raw or (probe.stderr or "").strip(),
                }
            ],
        }

    failures = [step for step in summary.get("steps", []) if not step.get("ok")]
    if not failures:
        print("[BugHunter] No failures detected")
        return summary

    logs = json.dumps(failures, indent=2)
    analysis = run_agent(
        "bugfinder",
        {
            "target": str(ROOT),
            "scope": "quick",
            "logs": logs,
        },
        model_override=BUG_HUNTER_MODEL,
    )
    message = analysis.get("result", "Bug hunter found failures")[:180]
    Executor().run(
        [
            {
                "type": "notify",
                "title": "Butler bug hunt",
                "message": message,
            }
        ]
    )
    notify("Butler bug hunt", message, subtitle="Blocker found")
    print(f"[BugHunter] {message}")
    return summary


def run_loop() -> None:
    interval_seconds = max(1, BUG_HUNTER_INTERVAL_MINUTES) * 60
    print(f"[BugHunter] Started - checking every {interval_seconds // 60} minutes")
    if not BUG_HUNTER_ENABLED:
        print("[BugHunter] Warning: BUG_HUNTER_ENABLED is False in butler_config.py")
    while True:
        run_bug_hunt_once()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Butler bug hunter")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously instead of a single pass",
    )
    args = parser.parse_args()

    if args.loop:
        run_loop()
    else:
        run_bug_hunt_once()
