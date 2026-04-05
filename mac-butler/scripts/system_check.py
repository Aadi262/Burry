#!/usr/bin/env python3
"""
scripts/system_check.py
Repeatable smoke checks for the Butler stack.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / "venv" / "bin" / "python")


def _run_command(
    name: str,
    command: list[str],
    timeout: int = 120,
    stdin_text: str | None = None,
) -> dict:
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            input=stdin_text,
            timeout=timeout,
        )
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        step = {
            "name": name,
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "duration_seconds": round(time.time() - started, 2),
            "output": output[-4000:],
            "command": command,
        }
        return _apply_validators(step)
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
        step = {
            "name": name,
            "ok": False,
            "returncode": None,
            "duration_seconds": round(time.time() - started, 2),
            "output": f"Timed out after {timeout}s\n{output[-3000:]}".strip(),
            "command": command,
        }
        return _apply_validators(step)


def _apply_validators(step: dict) -> dict:
    output = step.get("output", "")
    failure_markers = {
        "intent_router": ["traceback"],
        "agents_runner": ["status: error", "ollama not running", "traceback"],
        "executor_run_agent": ["'status': 'error'", "ollama not running", "traceback"],
        "heartbeat_once": ["[heartbeat] error", "ollama not running"],
        "butler_play": ["traceback"],
        "butler_open_project": ["traceback"],
        "butler_llm": ["traceback", "couldn't reach the brain", "ollama not running"],
        "butler_interactive": ["traceback"],
        "butler_briefing": ["traceback", "couldn't reach the brain", "ollama not running"],
        "butler_live": ["traceback", "couldn't reach the brain", "ollama not running"],
    }

    markers = failure_markers.get(step["name"], [])
    haystack = output.lower()
    if markers and any(marker in haystack for marker in markers):
        step["ok"] = False
    return step


def _run_confirmation_check() -> dict:
    command = [
        PYTHON,
        "-c",
        (
            "from executor.engine import Executor; "
            "e = Executor(); "
            "action = {'type': 'run_command', 'cmd': 'git push', 'cwd': '~/Burry/mac-butler'}; "
            "assert e._requires_confirmation(action) is True; "
            "e._ask_confirmation = lambda a: False; "
            "result = e.run([action]); "
            "print(result); "
            "assert result[0]['status'] == 'skipped'"
        ),
    ]
    return _run_command("confirmation_gate", command, timeout=30)


def _run_executor_agent_check() -> dict:
    command = [
        PYTHON,
        "-c",
        (
            "from executor.engine import Executor; "
            "result = Executor().run([{"
            "'type': 'run_agent', "
            "'agent': 'memory', "
            "'sessions': ["
            "{'timestamp': '2026-04-04T01:30', 'speech': 'Wired the planner'}, "
            "{'timestamp': '2026-04-04T02:00', 'speech': 'Testing the agent bridge'}"
            "]"
            "}]); "
            "print(result); "
            "assert result[0]['status'] == 'ok'"
        ),
    ]
    return _run_command("executor_run_agent", command, timeout=120)


def run_checks(include_live: bool = False) -> dict:
    steps = [
        _run_command(
            "unit_tests",
            [PYTHON, "-m", "unittest", "discover", "-s", "tests"],
            timeout=120,
        ),
        _run_command("intent_router", [PYTHON, "intents/router.py"], timeout=60),
        _run_command("agents_runner", [PYTHON, "agents/runner.py"], timeout=180),
        _run_executor_agent_check(),
        _run_confirmation_check(),
        _run_command("heartbeat_once", [PYTHON, "daemon/heartbeat.py"], timeout=120),
        _run_command(
            "butler_play",
            [PYTHON, "butler.py", "--test", "--command", "play lofi music"],
            timeout=120,
        ),
        _run_command(
            "butler_open_project",
            [PYTHON, "butler.py", "--test", "--command", "open mac-butler"],
            timeout=120,
        ),
        _run_command(
            "butler_llm",
            [PYTHON, "butler.py", "--test", "--command", "what should i do next"],
            timeout=120,
        ),
        _run_command(
            "butler_interactive",
            [PYTHON, "butler.py", "--interactive", "--test"],
            timeout=180,
            stdin_text=(
                "play mockingbird\n"
                "open cursor\n"
                "note: test the intent router tomorrow\n"
                "what am i working on\n"
                "pause music\n"
                "quit\n"
            ),
        ),
        _run_command(
            "butler_briefing",
            [PYTHON, "butler.py", "--test"],
            timeout=120,
        ),
    ]

    if include_live:
        steps.append(
            _run_command("butler_live", [PYTHON, "butler.py"], timeout=180)
        )

    return {
        "ok": all(step["ok"] for step in steps),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "steps": steps,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Butler smoke checks")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Include a full live butler run in the checks",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Alias for the default smoke sequence without the live run",
    )
    args = parser.parse_args()

    summary = run_checks(include_live=args.live)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for step in summary["steps"]:
            status = "PASS" if step["ok"] else "FAIL"
            print(f"[{status}] {step['name']}")
            if step["output"]:
                print(step["output"][:1200])
                print()
        print("Overall:", "PASS" if summary["ok"] else "FAIL")
    raise SystemExit(0 if summary["ok"] else 1)
