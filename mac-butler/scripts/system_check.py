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
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / "venv" / "bin" / "python")


def _stringify_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


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
        output = (_stringify_output(result.stdout) + "\n" + _stringify_output(result.stderr)).strip()
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
        output = (_stringify_output(exc.stdout) + "\n" + _stringify_output(exc.stderr)).strip()
        step = {
            "name": name,
            "ok": False,
            "returncode": None,
            "duration_seconds": round(time.time() - started, 2),
            "output": f"Timed out after {timeout}s\n{output[-3000:]}".strip(),
            "command": command,
        }
        return _apply_validators(step)


def _run_python_check(name: str, source: str, timeout: int = 120) -> dict:
    return _run_command(name, [PYTHON, "-c", source], timeout=timeout)


def _skipped_step(name: str, reason: str) -> dict:
    return {
        "name": name,
        "ok": True,
        "skipped": True,
        "returncode": 0,
        "duration_seconds": 0.0,
        "output": reason,
        "command": [],
    }


def _phase1_filesystem_check() -> dict:
    started = time.time()
    try:
        from executor.engine import Executor

        target = Path("/tmp/burry_phase1_smoke.txt")
        target.unlink(missing_ok=True)
        results = Executor().run(
            [
                {"type": "create_file", "path": str(target), "content": "phase1 smoke"},
                {
                    "type": "write_file",
                    "path": str(target),
                    "content": "phase1 smoke updated",
                    "mode": "append",
                },
            ]
        )
        target.unlink(missing_ok=True)
        ok = (
            len(results) == 2
            and all(item.get("status") == "ok" for item in results)
            and all(item.get("verification_status") == "verified" for item in results)
            and not target.exists()
        )
        return {
            "name": "phase1_filesystem",
            "ok": ok,
            "returncode": 0 if ok else 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": json.dumps(results, ensure_ascii=False),
            "command": ["internal", "phase1_filesystem_check"],
        }
    except Exception as exc:
        return {
            "name": "phase1_filesystem",
            "ok": False,
            "returncode": 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": str(exc),
            "command": ["internal", "phase1_filesystem_check"],
        }


def _phase1_calendar_read_check() -> dict:
    started = time.time()
    try:
        from executor.engine import Executor

        result = Executor().run([{"type": "calendar_read", "range": "today"}])[0]
        text = str(result.get("result", "")).lower()
        if "calendar automation access" in text:
            step = _skipped_step(
                "phase1_calendar_read",
                str(result.get("result", "")).strip()
                or "Skipped: Calendar automation access is not granted on this host.",
            )
            step["duration_seconds"] = round(time.time() - started, 2)
            return step
        ok = (
            result.get("status") == "ok"
            and "traceback" not in text
            and "syntax error" not in text
            and "execution error" not in text
        )
        return {
            "name": "phase1_calendar_read",
            "ok": ok,
            "returncode": 0 if ok else 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": json.dumps(result, ensure_ascii=False),
            "command": ["internal", "phase1_calendar_read_check"],
        }
    except Exception as exc:
        return {
            "name": "phase1_calendar_read",
            "ok": False,
            "returncode": 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": str(exc),
            "command": ["internal", "phase1_calendar_read_check"],
        }


def _cleanup_calendar_event(title: str) -> None:
    script = f'''
tell application "Calendar"
    repeat with c in calendars
        try
            repeat with e in (every event of c whose summary is {json.dumps(title)})
                delete e
            end repeat
        end try
    end repeat
end tell
'''
    try:
        subprocess.run(["osascript", "-e", script], cwd=str(ROOT), capture_output=True, text=True, timeout=8)
    except Exception:
        pass


def _cleanup_reminder(title: str) -> None:
    script = f'''
tell application "Reminders"
    repeat with reminderList in lists
        try
            repeat with reminderItem in reminders of reminderList
                if (name of reminderItem as string) is {json.dumps(title)} then delete reminderItem
            end repeat
        end try
    end repeat
end tell
'''
    try:
        subprocess.run(["osascript", "-e", script], cwd=str(ROOT), capture_output=True, text=True, timeout=8)
    except Exception:
        pass


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
        "phase1_calendar_read": ["traceback", "execution error", "syntax error", "not authorized"],
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


def _default_steps() -> list[dict]:
    return [
        _run_command(
            "unit_tests",
            [PYTHON, "-m", "unittest", "discover", "-s", "tests"],
            timeout=300,
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


def _phase1_host_steps(
    *,
    mail_to: str = "",
    whatsapp_contact: str = "",
    whatsapp_message: str = "",
) -> list[dict]:
    steps = [
        _phase1_filesystem_check(),
        _run_python_check(
            "phase1_browser",
            (
                "import json; "
                "from executor.engine import Executor; "
                "result = Executor().run([{'type': 'open_url_in_browser', 'url': 'https://example.com'}])[0]; "
                "print(json.dumps(result, ensure_ascii=False)); "
                "assert result['status'] == 'ok', result; "
                "assert result.get('verification_status') in {'verified', 'degraded'}, result; "
                "detail = str(result.get('verification_detail', '')).lower(); "
                "assert 'browser' in detail or 'page state' in detail, result"
            ),
            timeout=50,
        ),
        _run_python_check(
            "phase1_terminal",
            (
                "import json; "
                "from executor.engine import Executor; "
                "result = Executor().run([{'type': 'open_terminal', 'mode': 'window', 'cmd': 'echo burry-phase1-smoke', 'cwd': '~'}])[0]; "
                "print(json.dumps(result, ensure_ascii=False)); "
                "assert result['status'] == 'ok', result; "
                "assert result.get('verification_status') in {'verified', 'degraded'}, result; "
                "detail = str(result.get('verification_detail', '')).lower(); "
                "assert 'terminal' in detail, result"
            ),
            timeout=50,
        ),
        _phase1_calendar_read_check(),
        _run_python_check(
            "phase1_gmail_compose",
            (
                "import json; "
                "from executor.engine import Executor; "
                "result = Executor().run([{'type': 'compose_email', 'recipient': 'phase1@example.com', 'subject': 'Phase 1 smoke'}])[0]; "
                "print(json.dumps(result, ensure_ascii=False)); "
                "assert result['status'] == 'ok', result; "
                "assert result.get('verification_status') in {'verified', 'degraded'}, result; "
                "detail = str(result.get('verification_detail', '')).lower(); "
                "assert 'gmail compose' in detail or 'draft' in str(result.get('result', '')).lower(), result"
            ),
            timeout=50,
        ),
        _run_python_check(
            "phase1_whatsapp_open",
            (
                "import json; "
                "from executor.engine import Executor; "
                "result = Executor().run([{'type': 'whatsapp_open', 'contact': 'phase1 smoke'}])[0]; "
                "print(json.dumps(result, ensure_ascii=False)); "
                "assert result['status'] == 'ok', result; "
                "assert result.get('verification_status') in {'verified', 'degraded'}, result; "
                "detail = str(result.get('verification_detail', '')).lower(); "
                "assert 'whatsapp' in detail or 'browser' in detail, result"
            ),
            timeout=50,
        ),
        _run_python_check(
            "phase1_reminder",
            (
                "import json; "
                "from executor.engine import Executor; "
                "result = Executor().run([{'type': 'remind_in', 'minutes': 1, 'message': 'phase1 smoke'}])[0]; "
                "print(json.dumps(result, ensure_ascii=False)); "
                "assert result['status'] == 'ok', result; "
                "assert result.get('verification_status') == 'degraded', result; "
                "assert \"couldn't verify\" in str(result.get('verification_detail', '')).lower(), result"
            ),
            timeout=20,
        ),
    ]

    if mail_to:
        steps.append(
            _run_python_check(
                "phase1_mail_send",
                (
                    "import json; "
                    "from executor.engine import Executor; "
                    f"result = Executor().run([{{'type': 'send_email', 'to': {json.dumps(mail_to)}, 'subject': 'Burry Phase 1 smoke', 'body': 'Phase 1 smoke validation.'}}])[0]; "
                    "print(json.dumps(result, ensure_ascii=False)); "
                    "assert result['status'] == 'ok', result; "
                    "assert result.get('verification_status') == 'degraded', result; "
                    "assert 'couldn\\'t confirm delivery' in str(result.get('verification_detail', '')).lower(), result"
                ),
                timeout=40,
            )
        )
    else:
        steps.append(
            _skipped_step(
                "phase1_mail_send",
                "Skipped: pass --mail-to to exercise the real Mail delivery path.",
            )
        )

    if whatsapp_contact and whatsapp_message:
        steps.append(
            _run_python_check(
                "phase1_whatsapp_send",
                (
                    "import json; "
                    "from executor.engine import Executor; "
                    f"result = Executor().run([{{'type': 'send_whatsapp', 'contact': {json.dumps(whatsapp_contact)}, 'message': {json.dumps(whatsapp_message)}}}])[0]; "
                    "print(json.dumps(result, ensure_ascii=False)); "
                    "assert result['status'] == 'ok', result; "
                    "assert result.get('verification_status') == 'degraded', result; "
                    "assert 'couldn\\'t confirm' in str(result.get('verification_detail', '')).lower(), result"
                ),
                timeout=40,
            )
        )
    else:
        steps.append(
            _skipped_step(
                "phase1_whatsapp_send",
                "Skipped: pass --whatsapp-contact and --whatsapp-message to exercise the real WhatsApp send path.",
            )
        )

    return steps


def _phase3a_filesystem_check() -> dict:
    started = time.time()
    try:
        from executor.engine import Executor

        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            root = Path(tmpdir)
            desktop = root / "Desktop"
            documents = root / "Documents"
            downloads = root / "Downloads"
            workspace = root / "Workspace"
            desktop.mkdir()
            documents.mkdir()
            downloads.mkdir()
            workspace.mkdir()

            executor = Executor()
            executor._filesystem_search_roots = lambda preferred_root="": [desktop, documents, downloads, workspace]
            executor._speak = lambda *_args, **_kwargs: None
            executor._listen_followup = lambda timeout=5.0: "yes"
            source_path = downloads / "phase3a-source.txt"
            workspace_path = workspace / "phase3a-source.txt"
            results = executor.run(
                [
                    {"type": "create_file", "path": str(source_path), "content": "phase3a"},
                    {"type": "move_file", "from": str(source_path), "to": str(workspace)},
                    {"type": "copy_file", "from": str(workspace_path), "to": str(documents)},
                    {"type": "zip_folder", "path": str(documents)},
                    {"type": "delete_file", "path": str(workspace_path)},
                ]
            )
            ok = (
                len(results) == 5
                and all(item.get("status") == "ok" for item in results)
                and all(item.get("verification_status") == "verified" for item in results)
                and (documents / "phase3a-source.txt").exists()
                and (documents.parent / "Documents.zip").exists()
                and not workspace_path.exists()
                and not source_path.exists()
            )
            return {
                "name": "phase3a_filesystem",
                "ok": ok,
                "returncode": 0 if ok else 1,
                "duration_seconds": round(time.time() - started, 2),
                "output": json.dumps(results, ensure_ascii=False),
                "command": ["internal", "phase3a_filesystem_check"],
            }
    except Exception as exc:
        return {
            "name": "phase3a_filesystem",
            "ok": False,
            "returncode": 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": str(exc),
            "command": ["internal", "phase3a_filesystem_check"],
        }


def _phase3a_browser_check() -> dict:
    started = time.time()
    try:
        from executor.engine import Executor

        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            root = Path(tmpdir)
            page_one = root / "phase3a-browser-1.html"
            page_two = root / "phase3a-browser-2.html"
            page_three = root / "phase3a-browser-3.html"
            page_one.write_text("<html><body><h1>Phase 3A Browser 1</h1></body></html>", encoding="utf-8")
            page_two.write_text("<html><body><h1>Phase 3A Browser 2</h1></body></html>", encoding="utf-8")
            page_three.write_text("<html><body><h1>Phase 3A Browser 3</h1></body></html>", encoding="utf-8")

            actions = [
                {"type": "open_url_in_browser", "url": page_one.resolve().as_uri()},
                {"type": "browser_go_to", "url": page_two.resolve().as_uri()},
                {"type": "browser_go_back"},
                {"type": "browser_refresh"},
                {"type": "browser_window", "url": page_three.resolve().as_uri()},
            ]
            results = Executor().run(actions)
            ok = (
                len(results) == 5
                and all(item.get("status") == "ok" for item in results)
                and all(item.get("verification_status") in {"verified", "degraded"} for item in results)
            )
            return {
                "name": "phase3a_browser",
                "ok": ok,
                "returncode": 0 if ok else 1,
                "duration_seconds": round(time.time() - started, 2),
                "output": json.dumps(results, ensure_ascii=False),
                "command": ["internal", "phase3a_browser_check"],
            }
    except Exception as exc:
        return {
            "name": "phase3a_browser",
            "ok": False,
            "returncode": 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": str(exc),
            "command": ["internal", "phase3a_browser_check"],
        }


def _phase3a_calendar_write_check() -> dict:
    started = time.time()
    title = f"Burry Phase 3A Calendar Smoke {int(started)}"
    try:
        from executor.engine import Executor

        result = Executor().run([{"type": "calendar_add", "title": title, "time": "tomorrow 9am", "duration": 15}])[0]
        text = json.dumps(result, ensure_ascii=False)
        detail = str(result.get("result", "")).lower()
        if "calendar event creation is unavailable until calendar automation access is granted on this host" in detail:
            step = _skipped_step("phase3a_calendar_add", str(result.get("result", "")).strip())
            step["duration_seconds"] = round(time.time() - started, 2)
            return step
        ok = result.get("status") == "ok" and result.get("verification_status") == "verified"
        return {
            "name": "phase3a_calendar_add",
            "ok": ok,
            "returncode": 0 if ok else 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": text,
            "command": ["internal", "phase3a_calendar_write_check"],
        }
    except Exception as exc:
        return {
            "name": "phase3a_calendar_add",
            "ok": False,
            "returncode": 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": str(exc),
            "command": ["internal", "phase3a_calendar_write_check"],
        }
    finally:
        _cleanup_calendar_event(title)


def _phase3a_reminder_check() -> dict:
    started = time.time()
    title = f"Burry Phase 3A Reminder Smoke {int(started)}"
    try:
        from executor.engine import Executor

        result = Executor().run([{"type": "set_reminder", "minutes": 30, "message": title}])[0]
        text = json.dumps(result, ensure_ascii=False)
        detail = str(result.get("result", "")).lower()
        if "reminder creation is unavailable until reminders automation access is granted on this host" in detail:
            step = _skipped_step("phase3a_reminder", str(result.get("result", "")).strip())
            step["duration_seconds"] = round(time.time() - started, 2)
            return step
        ok = result.get("status") == "ok" and result.get("verification_status") == "verified"
        return {
            "name": "phase3a_reminder",
            "ok": ok,
            "returncode": 0 if ok else 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": text,
            "command": ["internal", "phase3a_reminder_check"],
        }
    except Exception as exc:
        return {
            "name": "phase3a_reminder",
            "ok": False,
            "returncode": 1,
            "duration_seconds": round(time.time() - started, 2),
            "output": str(exc),
            "command": ["internal", "phase3a_reminder_check"],
        }
    finally:
        _cleanup_reminder(title)


def _phase3a_host_steps(*, allow_disruptive_system: bool = False) -> list[dict]:
    steps = [
        _phase3a_filesystem_check(),
        _phase3a_browser_check(),
        _phase3a_calendar_write_check(),
        _phase3a_reminder_check(),
        _run_python_check(
            "phase3a_system_safe",
            (
                "import json, os; "
                "from executor.engine import Executor; "
                "screenshot = Executor().take_screenshot(save=True, describe=False); "
                "battery = Executor().system_info('battery'); "
                "wifi = Executor().system_info('wifi'); "
                "print(json.dumps({'screenshot': screenshot, 'battery': battery, 'wifi': wifi}, ensure_ascii=False)); "
                "assert os.path.exists(screenshot), screenshot; "
                "assert str(battery).strip(), battery; "
                "assert str(wifi).strip(), wifi"
            ),
            timeout=40,
        ),
    ]

    if allow_disruptive_system:
        steps.append(
            _run_python_check(
                "phase3a_system_disruptive",
                (
                    "import json; "
                    "from executor.engine import Executor; "
                    "actions = ["
                    " {'type': 'volume_set', 'level': 20}, "
                    " {'type': 'system_volume', 'direction': 'up'}, "
                    " {'type': 'brightness', 'level': 60}, "
                    " {'type': 'brightness', 'direction': 'down'}, "
                    " {'type': 'dark_mode', 'enable': True}, "
                    " {'type': 'dark_mode', 'enable': False}, "
                    " {'type': 'do_not_disturb', 'enable': True}, "
                    " {'type': 'do_not_disturb', 'enable': False}, "
                    " {'type': 'show_desktop'}"
                    "]; "
                    "results = Executor().run(actions); "
                    "print(json.dumps(results, ensure_ascii=False)); "
                    "assert all(item['status'] == 'ok' for item in results), results"
                ),
                timeout=60,
            )
        )
    else:
        steps.append(
            _skipped_step(
                "phase3a_system_disruptive",
                "Skipped: pass --phase3a-allow-disruptive-system to exercise volume, brightness, dark-mode, DND, and show-desktop host paths.",
            )
        )

    return steps


def run_checks(
    include_live: bool = False,
    *,
    include_phase1_host: bool = False,
    phase1_host_only: bool = False,
    include_phase3a_host: bool = False,
    phase3a_host_only: bool = False,
    mail_to: str = "",
    whatsapp_contact: str = "",
    whatsapp_message: str = "",
    allow_disruptive_system: bool = False,
) -> dict:
    host_only = phase1_host_only or phase3a_host_only
    steps = [] if host_only else _default_steps()

    if include_live:
        steps.append(
            _run_command("butler_live", [PYTHON, "butler.py"], timeout=180)
        )

    if include_phase1_host:
        steps.extend(
            _phase1_host_steps(
                mail_to=mail_to,
                whatsapp_contact=whatsapp_contact,
                whatsapp_message=whatsapp_message,
            )
        )

    if include_phase3a_host:
        steps.extend(
            _phase3a_host_steps(
                allow_disruptive_system=allow_disruptive_system,
            )
        )

    return {
        "ok": all(step["ok"] for step in steps if not step.get("skipped")),
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
    parser.add_argument(
        "--phase1-host",
        action="store_true",
        help="Run the Phase 1 host smoke checks for filesystem, browser, terminal, calendar, Gmail, WhatsApp, and reminders.",
    )
    parser.add_argument(
        "--phase1-host-only",
        action="store_true",
        help="Run only the Phase 1 host smoke checks and skip the default smoke sequence.",
    )
    parser.add_argument(
        "--phase3a-host",
        action="store_true",
        help="Run the Phase 3A host smoke checks for broader filesystem coverage, browser actions, calendar write, reminders, and safe system-control paths.",
    )
    parser.add_argument(
        "--phase3a-host-only",
        action="store_true",
        help="Run only the Phase 3A host smoke checks and skip the default smoke sequence.",
    )
    parser.add_argument(
        "--phase3a-allow-disruptive-system",
        action="store_true",
        help="Also run the disruptive Phase 3A system smoke checks for volume, brightness, dark mode, DND, and show desktop.",
    )
    parser.add_argument(
        "--mail-to",
        default="",
        help="Optional email address for the real Mail send smoke step.",
    )
    parser.add_argument(
        "--whatsapp-contact",
        default="",
        help="Optional WhatsApp contact for the real send smoke step.",
    )
    parser.add_argument(
        "--whatsapp-message",
        default="",
        help="Optional WhatsApp message for the real send smoke step.",
    )
    args = parser.parse_args()

    summary = run_checks(
        include_live=args.live,
        include_phase1_host=args.phase1_host,
        phase1_host_only=args.phase1_host_only,
        include_phase3a_host=args.phase3a_host,
        phase3a_host_only=args.phase3a_host_only,
        mail_to=args.mail_to,
        whatsapp_contact=args.whatsapp_contact,
        whatsapp_message=args.whatsapp_message,
        allow_disruptive_system=args.phase3a_allow_disruptive_system,
    )
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
