#!/usr/bin/env python3
"""Project dashboard generator and tiny local server."""

from __future__ import annotations

import asyncio
import json
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

try:
    import websockets
except ImportError:
    websockets = None

try:
    from .github_sync import get_github_context
    from .open_project import open_project
    from .project_store import load_projects
    from .project_store import _load_raw as _load_projects_raw
except ImportError:
    from github_sync import get_github_context
    from open_project import open_project
    from project_store import load_projects
    from project_store import _load_raw as _load_projects_raw
from utils import _clip_text

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DASHBOARD_PATH = ROOT / "dashboard.html"
FRONTEND_ROOT = ROOT / "frontend"
FRONTEND_INDEX_PATH = FRONTEND_ROOT / "index.html"
FRONTEND_STYLE_PATH = FRONTEND_ROOT / "style.css"
FRONTEND_APP_PATH = FRONTEND_ROOT / "app.js"
FRONTEND_MODULES_ROOT = FRONTEND_ROOT / "modules"
FRONTEND_VENDOR_ROOT = FRONTEND_ROOT / "vendor"
MAC_STATE_PATH = PROJECT_ROOT / "memory" / "mac_state.json"
GRAPH_PATH = PROJECT_ROOT / "memory" / "layers" / "graph.json"
TASKS_PATH = PROJECT_ROOT / "tasks" / "tasks.json"
NATIVE_SHELL_PATH = ROOT / "native_shell.py"
HUD_PID_PATH = Path("/tmp/burry_hud.pid")
HUD_LOG_PATH = Path("/tmp/burry_hud.log")
HOST = "127.0.0.1"
PREFERRED_PORT = 3333
WS_PREFERRED_PORT = 3334
PORT = PREFERRED_PORT
WS_PORT = WS_PREFERRED_PORT
USE_NATIVE_HUD = os.environ.get("BURRY_USE_NATIVE_HUD", "").strip().lower() in {"1", "true", "yes", "on"}
_SERVER: ThreadingHTTPServer | None = None
_SERVER_THREAD: threading.Thread | None = None
_SERVER_LOCK = threading.Lock()
_WINDOW_LOCK = threading.Lock()
_LAST_WINDOW_OPENED_AT = 0.0
STREAM_INTERVAL_SECONDS = 0.35
_WS_LOOP: asyncio.AbstractEventLoop | None = None
_WS_SERVER_THREAD: threading.Thread | None = None
_WS_CLIENTS: set = set()
_WS_CLIENTS_LOCK = threading.Lock()
_WS_WATCHER_THREAD: threading.Thread | None = None
_VPS_CACHE_LOCK = threading.Lock()
_VPS_CACHE_PAYLOAD: dict | None = None
_VPS_CACHE_AT = 0.0
_VPS_CACHE_TTL_SECONDS = 30.0


def _status_rank(status: str) -> int:
    return {"active": 0, "paused": 1, "done": 2}.get(status, 9)


def _dashboard_projects() -> list[dict]:
    try:
        raw_projects = _load_projects_raw()
    except Exception:
        raw_projects = []

    projects: list[dict] = []
    for project in raw_projects:
        item = dict(project)
        item["status"] = str(item.get("status", "paused") or "paused")
        try:
            item["completion"] = int(item.get("completion", 0) or 0)
        except Exception:
            item["completion"] = 0
        item["health_status"] = str(item.get("health_status", "unknown") or "unknown")
        item["next_tasks"] = list(item.get("next_tasks") or [])
        item["blockers"] = list(item.get("blockers") or [])
        item["description"] = str(item.get("description", "") or item.get("deploy_target", "") or "Local operator project")
        item["blurb"] = str(item.get("blurb", "") or "")
        projects.append(item)
    return projects


def _dashboard_github_context(projects: list[dict]) -> str:
    items = []
    for project in projects:
        repo = project.get("repo")
        if not repo:
            continue
        commit = str(project.get("last_commit") or "unknown")[:10]
        try:
            issues = int(project.get("open_issues", 0) or 0)
        except Exception:
            issues = 0
        items.append(f"{project.get('name')}: {commit}/{issues}i")
    if not items:
        return ""
    return ("[GITHUB]\n" + " | ".join(items))[:350]


def _select_port(preferred: int = PREFERRED_PORT, exclude: set[int] | None = None) -> int:
    blocked = set(exclude or set())
    for candidate in range(preferred, preferred + 12):
        if candidate in blocked:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((HOST, candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def dashboard_url() -> str:
    return f"http://{HOST}:{PORT}"


def dashboard_ws_url() -> str:
    return f"ws://{HOST}:{WS_PORT}/ws"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json_file(path: Path, fallback):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return payload if isinstance(payload, type(fallback)) else fallback


def _mac_activity_payload() -> dict:
    return _load_json_file(MAC_STATE_PATH, {})


def _graph_payload() -> dict:
    return _load_json_file(GRAPH_PATH, {})


def _tasks_payload() -> dict:
    return _load_json_file(TASKS_PATH, {})


def _vps_payload() -> dict:
    global _VPS_CACHE_PAYLOAD, _VPS_CACHE_AT

    now = time.monotonic()
    with _VPS_CACHE_LOCK:
        if _VPS_CACHE_PAYLOAD is not None and now - _VPS_CACHE_AT < _VPS_CACHE_TTL_SECONDS:
            return dict(_VPS_CACHE_PAYLOAD)

    remote_command = (
        "python3 -c 'import json, os, shutil; from pathlib import Path; "
        "load = os.getloadavg()[0] if hasattr(os, \"getloadavg\") else 0.0; "
        "cores = os.cpu_count() or 1; "
        "cpu = round(min(100.0, (load / cores) * 100.0), 1); "
        "page = os.sysconf(\"SC_PAGE_SIZE\"); "
        "phys = os.sysconf(\"SC_PHYS_PAGES\"); "
        "avail = os.sysconf(\"SC_AVPHYS_PAGES\"); "
        "total = page * phys; "
        "free = page * avail; "
        "used = max(0, total - free); "
        "memory = round((used / total) * 100.0, 1) if total else 0.0; "
        "disk_total, disk_used, _ = shutil.disk_usage(\"/\"); "
        "disk = round((disk_used / disk_total) * 100.0, 1) if disk_total else 0.0; "
        "uptime = \"\"; "
        "path = Path(\"/proc/uptime\"); "
        "uptime = str(int(float(path.read_text().split()[0]))) if path.exists() else \"\"; "
        "print(json.dumps({\"status\": \"online\", \"cpu\": cpu, \"memory\": memory, \"disk\": disk, \"uptime\": uptime}))'"
    )
    offline = {"status": "offline", "cpu": None, "memory": None, "disk": None, "uptime": ""}
    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "vps.py"), "exec", remote_command],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            payload = offline
        else:
            payload = json.loads(str(result.stdout or "").strip() or "{}")
            if not isinstance(payload, dict):
                payload = offline
    except Exception:
        payload = offline

    with _VPS_CACHE_LOCK:
        _VPS_CACHE_PAYLOAD = dict(payload)
        _VPS_CACHE_AT = now
    return dict(payload)


def _status_tone(status: str) -> str:
    lowered = str(status or "").lower()
    if lowered in {"live", "ready", "healthy", "online", "active"}:
        return "healthy"
    if lowered in {"standby", "pending", "local", "vps", "configured", "disabled"}:
        return "degraded"
    return "offline"


def _workspace_project_name(workspace: str, projects: list[dict]) -> str:
    candidate = str(workspace or "").strip()
    if not candidate:
        return ""
    try:
        candidate_path = Path(os.path.expanduser(candidate)).resolve(strict=False)
    except Exception:
        return Path(candidate).name

    best: tuple[int, str] | None = None
    for project in projects:
        try:
            root = Path(os.path.expanduser(str(project.get("path", "") or ""))).resolve(strict=False)
        except Exception:
            continue
        try:
            if candidate_path == root or root in candidate_path.parents:
                score = len(str(root))
                name = str(project.get("name", "")).strip()
                if name and (best is None or score > best[0]):
                    best = (score, name)
        except Exception:
            continue
    return best[1] if best else candidate_path.name


def _url_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=1.0) as response:
            return int(getattr(response, "status", 200)) < 500
    except URLError:
        return False
    except Exception:
        return False


def _wait_for_dashboard_health(url: str, timeout: float = 6.0) -> bool:
    health_url = f"{url.rstrip('/')}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _url_ok(health_url):
            return True
        time.sleep(0.15)
    return False


def operator_snapshot(projects: list[dict] | None = None) -> dict:
    try:
        from butler_config import MCP_SERVERS, OLLAMA_LOCAL_URL, SEARXNG_URL, USE_VPS_OLLAMA, VPS_OLLAMA_URL
    except Exception:
        MCP_SERVERS = {}
        OLLAMA_LOCAL_URL = "http://localhost:11434"
        SEARXNG_URL = "http://localhost:8080"
        USE_VPS_OLLAMA = False
        VPS_OLLAMA_URL = ""

    try:
        from context.mac_activity import load_state as load_mac_state
    except Exception:
        load_mac_state = lambda: {}

    try:
        from mcp.client import get_server_status
    except Exception:
        get_server_status = None

    try:
        from runtime import load_runtime_state
    except Exception:
        load_runtime_state = lambda: {}

    try:
        from brain.mood_engine import describe_mood_state
    except Exception:
        describe_mood_state = lambda: {"name": "focused", "label": "Focused", "note": "Locked on the next concrete step."}

    try:
        from tasks import get_active_tasks
    except Exception:
        get_active_tasks = lambda project=None: []

    try:
        from voice import describe_stt, describe_tts
    except Exception:
        describe_stt = lambda: {"backend": "unavailable", "active_model": ""}
        describe_tts = lambda: {"backend": "unavailable", "voice": ""}

    catalog = projects if projects is not None else _dashboard_projects()
    runtime_state = load_runtime_state() or {}
    mac_state = load_mac_state() or {}
    mood_state = describe_mood_state() or {}
    runtime_workspace = runtime_state.get("workspace") if isinstance(runtime_state.get("workspace"), dict) else {}
    workspace = str(runtime_workspace.get("workspace", "") or mac_state.get("cursor_workspace", "") or "").strip()
    focus_project = str(runtime_workspace.get("focus_project", "") or "").strip() or _workspace_project_name(workspace, catalog)
    frontmost_app = str(runtime_workspace.get("frontmost_app", "") or mac_state.get("frontmost_app", "") or "").strip()

    tasks = []
    try:
        active_tasks = get_active_tasks(focus_project or None)
    except Exception:
        active_tasks = []
    for task in active_tasks[:3]:
        title = _clip_text(task.get("title", ""), limit=72)
        if title:
            tasks.append(title)

    stt = describe_stt() or {}
    tts = describe_tts() or {}
    search_online = _url_ok(f"{SEARXNG_URL}/")
    voice_backend = str(tts.get("backend", "unavailable")).lower()
    listen_backend = str(stt.get("backend", "pending")).lower()
    systems = [
        {
            "name": "Brain",
            "status": "vps" if USE_VPS_OLLAMA else "local",
            "detail": VPS_OLLAMA_URL if USE_VPS_OLLAMA else OLLAMA_LOCAL_URL,
            "tone": _status_tone("vps" if USE_VPS_OLLAMA else "local"),
        },
        {
            "name": "Search",
            "status": "online" if search_online else "offline",
            "detail": "SearXNG",
            "tone": _status_tone("online" if search_online else "offline"),
        },
        {
            "name": "Voice",
            "status": voice_backend,
            "detail": str(tts.get("voice", "") or tts.get("rate", "")).strip(),
            "tone": _status_tone("healthy" if voice_backend in {"edge", "kokoro", "say"} else "offline"),
        },
        {
            "name": "Listen",
            "status": listen_backend,
            "detail": str(stt.get("active_model", "") or stt.get("requested_model", "")).strip(),
            "tone": _status_tone("healthy" if listen_backend in {"mlx", "faster"} else "pending"),
        },
    ]

    mcp_rows = []
    for server_name in sorted(MCP_SERVERS):
        if get_server_status is None:
            mcp_rows.append(
                {
                    "name": server_name,
                    "status": "unavailable",
                    "detail": "MCP client unavailable",
                    "tone": "offline",
                }
            )
            continue

        status = get_server_status(server_name)
        if status.get("ready"):
            label = "ready"
            detail = "Connected"
        elif status.get("enabled") and status.get("configured"):
            missing = ", ".join(status.get("missing_env") or []) or "runtime"
            label = "needs secrets"
            detail = missing
        elif status.get("configured"):
            label = "configured"
            detail = "Disabled"
        else:
            label = "missing"
            detail = "No command configured"
        mcp_rows.append(
            {
                "name": server_name,
                "status": label,
                "detail": detail,
                "tone": _status_tone(label),
            }
        )

    events = list(runtime_state.get("events") or [])[-10:]
    last_intent = runtime_state.get("last_intent") or {}
    last_agent_result = runtime_state.get("last_agent_result") if isinstance(runtime_state.get("last_agent_result"), dict) else {}
    memory_recall = runtime_state.get("last_memory_recall") if isinstance(runtime_state.get("last_memory_recall"), dict) else {}
    tool_stream = list(runtime_state.get("tool_stream") or [])[-6:]
    active_tools = [str(item).strip() for item in list(runtime_state.get("active_tools") or []) if str(item).strip()]
    ambient_context = [
        _clip_text(item, limit=140)
        for item in list(runtime_state.get("ambient_context") or [])[:3]
        if _clip_text(item, limit=140)
    ]
    state_name = str(runtime_state.get("state", "idle") or "idle").strip().lower()
    session_active = bool(runtime_state.get("session_active"))
    session_label = "live" if session_active else "standby"

    return {
        "state": state_name,
        "state_label": state_name.title(),
        "state_tone": _status_tone("active" if state_name in {"listening", "thinking", "speaking"} else "pending"),
        "session_active": session_active,
        "session_label": session_label,
        "session_tone": _status_tone(session_label),
        "mood": str(mood_state.get("name", "") or "focused"),
        "mood_label": str(mood_state.get("label", "") or "Focused"),
        "mood_note": str(mood_state.get("note", "") or ""),
        "updated_at": str(runtime_state.get("updated_at", "") or _timestamp()),
        "last_heard_text": str(runtime_state.get("last_heard_text", "") or ""),
        "last_heard_at": str(runtime_state.get("last_heard_at", "") or ""),
        "last_spoken_text": str(runtime_state.get("last_spoken_text", "") or ""),
        "last_spoken_at": str(runtime_state.get("last_spoken_at", "") or ""),
        "last_intent_name": str(last_intent.get("name", "") or ""),
        "last_intent_confidence": float(last_intent.get("confidence", 0.0) or 0.0),
        "focus_project": focus_project,
        "frontmost_app": frontmost_app,
        "workspace": workspace,
        "spotify_track": _clip_text(mac_state.get("spotify_track", ""), limit=80),
        "browser_url": _clip_text(mac_state.get("browser_url", ""), limit=80),
        "tasks": tasks,
        "systems": systems,
        "mcp": mcp_rows,
        "active_tools": active_tools[:4],
        "tool_stream": tool_stream,
        "memory_recall": memory_recall,
        "ambient_context": ambient_context,
        "last_agent_result": last_agent_result,
        "events": events,
    }


def generate_dashboard() -> str:
    """Return the live Burry HUD HTML with bootstrap data."""
    bootstrap = _dashboard_payload()
    bootstrap_json = json.dumps(bootstrap).replace("</", "<\\/")
    asset_stamp = str(int(time.time()))

    try:
        template = FRONTEND_INDEX_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "<!doctype html><html><body>"
            "<h1>Burry Live Operator</h1>"
            "<p>Frontend template is missing.</p>"
            f"<script id='burry-bootstrap' type='application/json'>{bootstrap_json}</script>"
            "</body></html>"
        )

    html = template.replace("__BURRY_BOOTSTRAP_JSON__", bootstrap_json)
    html = html.replace('/style.css"', f'/style.css?v={asset_stamp}"')
    html = html.replace('/app.js"', f'/app.js?v={asset_stamp}"')
    return html


def _dashboard_payload() -> dict:
    projects = _dashboard_projects()
    return {
        "projects": projects,
        "operator": operator_snapshot(projects),
        "wsUrl": dashboard_ws_url(),
        "githubContext": _dashboard_github_context(projects),
        "generatedAt": _timestamp(),
    }


def _dispatch_command(text: str) -> None:
    try:
        from butler import handle_input
    except Exception as exc:
        print(f"[dashboard] command dispatch unavailable: {exc}")
        return

    try:
        handle_input(text, test_mode=False)
    except Exception as exc:
        print(f"[dashboard] command dispatch failed: {exc}")


def _dispatch_listen_once() -> None:
    try:
        from butler import handle_input
        from voice.stt import listen_for_command
    except Exception as exc:
        print(f"[dashboard] listen dispatch unavailable: {exc}")
        return

    try:
        text = " ".join(str(listen_for_command(timeout=10.0) or "").split()).strip()
        if text:
            handle_input(text, test_mode=False)
    except Exception as exc:
        print(f"[dashboard] listen dispatch failed: {exc}")


def _write_dashboard() -> None:
    DASHBOARD_PATH.write_text(generate_dashboard(), encoding="utf-8")


def _event_stream_message(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(",", ":"))
    return f"data: {body}\n\n".encode("utf-8")


def _ws_message(message_type: str, payload: dict | list) -> str:
    return json.dumps(
        {"type": message_type, "payload": payload},
        separators=(",", ":"),
    )


async def _ws_handler(websocket) -> None:
    path = getattr(getattr(websocket, "request", None), "path", "/ws")
    if path != "/ws":
        await websocket.close(code=1008, reason="Invalid path")
        return

    with _WS_CLIENTS_LOCK:
        _WS_CLIENTS.add(websocket)

    try:
        await websocket.send(_ws_message("operator", operator_snapshot()))
        await websocket.send(_ws_message("projects", _dashboard_projects()))
        await websocket.wait_closed()
    finally:
        with _WS_CLIENTS_LOCK:
            _WS_CLIENTS.discard(websocket)


async def _ws_broadcast(message: str) -> None:
    with _WS_CLIENTS_LOCK:
        clients = list(_WS_CLIENTS)

    stale = []
    for client in clients:
        try:
            await client.send(message)
        except Exception:
            stale.append(client)

    if stale:
        with _WS_CLIENTS_LOCK:
            for client in stale:
                _WS_CLIENTS.discard(client)


def _broadcast_operator_snapshot(payload: dict | None = None) -> None:
    if _WS_LOOP is None or not _WS_LOOP.is_running():
        return
    message = _ws_message("operator", payload or operator_snapshot())
    asyncio.run_coroutine_threadsafe(_ws_broadcast(message), _WS_LOOP)


def _broadcast_projects_snapshot(payload: list[dict] | None = None) -> None:
    if _WS_LOOP is None or not _WS_LOOP.is_running():
        return
    message = _ws_message("projects", payload or _dashboard_projects())
    asyncio.run_coroutine_threadsafe(_ws_broadcast(message), _WS_LOOP)


def _watch_operator_state() -> None:
    last_operator_payload = ""
    last_projects_payload = ""
    last_projects_check_at = 0.0
    while True:
        with _WS_CLIENTS_LOCK:
            has_clients = bool(_WS_CLIENTS)
        if not has_clients:
            time.sleep(0.2)
            continue

        operator_payload = operator_snapshot()
        operator_encoded = json.dumps(operator_payload, sort_keys=True, separators=(",", ":"))
        if operator_encoded != last_operator_payload:
            _broadcast_operator_snapshot(operator_payload)
            last_operator_payload = operator_encoded

        now = time.monotonic()
        if now - last_projects_check_at >= 1.0:
            projects_payload = _dashboard_projects()
            projects_encoded = json.dumps(projects_payload, sort_keys=True, separators=(",", ":"))
            if projects_encoded != last_projects_payload:
                _broadcast_projects_snapshot(projects_payload)
                last_projects_payload = projects_encoded
            last_projects_check_at = now
        time.sleep(0.12)


def _start_ws_watcher() -> None:
    global _WS_WATCHER_THREAD
    if _WS_WATCHER_THREAD is not None and _WS_WATCHER_THREAD.is_alive():
        return
    _WS_WATCHER_THREAD = threading.Thread(target=_watch_operator_state, daemon=True, name="burry-ws-watch")
    _WS_WATCHER_THREAD.start()


def _run_ws_server() -> None:
    global _WS_LOOP

    loop = asyncio.new_event_loop()
    _WS_LOOP = loop
    asyncio.set_event_loop(loop)

    async def _serve():
        return await websockets.serve(_ws_handler, HOST, WS_PORT)

    server = loop.run_until_complete(_serve())
    try:
        loop.run_forever()
    finally:
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.close()


def _start_ws_server() -> bool:
    global _WS_SERVER_THREAD, WS_PORT

    if websockets is None:
        return False
    if _WS_SERVER_THREAD is not None and _WS_SERVER_THREAD.is_alive():
        return True

    WS_PORT = _select_port(WS_PREFERRED_PORT, exclude={PORT})
    _WS_SERVER_THREAD = threading.Thread(target=_run_ws_server, daemon=True, name="burry-ws")
    _WS_SERVER_THREAD.start()
    for _ in range(40):
        if _WS_LOOP is not None and _WS_LOOP.is_running():
            break
        time.sleep(0.05)
    _start_ws_watcher()
    return True


def _serve_asset(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    if not path.exists():
        handler.send_response(404)
        handler.end_headers()
        return
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        return


def _native_shell_available() -> bool:
    return NATIVE_SHELL_PATH.exists() and importlib.util.find_spec("webview") is not None


def _native_shell_running() -> bool:
    if not HUD_PID_PATH.exists():
        return False
    try:
        pid = int(HUD_PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _spawn_native_shell(url: str) -> bool:
    if not _native_shell_available():
        return False
    if _native_shell_running():
        return True
    if not _wait_for_dashboard_health(url):
        return False

    HUD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HUD_LOG_PATH.open("ab") as log_file:
        subprocess.Popen(
            [sys.executable, str(NATIVE_SHELL_PATH), "--url", url, "--title", "Burry"],
            cwd=str(ROOT.parent),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
    return True


def _open_browser_window(url: str) -> None:
    chrome_like_apps = ["Google Chrome", "Brave Browser", "Chromium"]
    for app_name in chrome_like_apps:
        try:
            result = subprocess.run(
                [
                    "open",
                    "-na",
                    app_name,
                    "--args",
                    f"--app={url}",
                    "--new-window",
                    "--window-size=1560,980",
                ],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if result.returncode == 0:
                return
        except Exception:
            continue

    try:
        webbrowser.open(url)
    except Exception:
        pass


def serve_dashboard():
    """
    Starts a simple HTTP server on localhost:3333.
    GET /api/projects → returns projects.json as JSON
    GET / → serves dashboard.html
    Runs in background thread so it doesn't block Butler.
    """

    global _SERVER, _SERVER_THREAD, PORT
    with _SERVER_LOCK:
        if _SERVER is not None and _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
            _start_ws_server()
            _write_dashboard()
            return _SERVER

        class Handler(BaseHTTPRequestHandler):
            def _safe_write(self, body: bytes) -> None:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    return

            def _read_json_body(self) -> dict:
                try:
                    content_length = int(self.headers.get("Content-Length", "0") or 0)
                except Exception:
                    content_length = 0
                if content_length <= 0:
                    return {}
                try:
                    raw = self.rfile.read(content_length)
                except Exception:
                    return {}
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    return {}
                return payload if isinstance(payload, dict) else {}

            def _send_text(self, body: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self._safe_write(payload)

            def _send_json(self, payload: dict | list, status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body)

            def do_GET(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    if parsed.path == "/health":
                        self._send_json({"ok": True, "url": dashboard_url(), "port": PORT, "ws_url": dashboard_ws_url()})
                        return
                    if parsed.path == "/api/stream":
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "keep-alive")
                        self.end_headers()

                        last_payload = None
                        while True:
                            payload = operator_snapshot()
                            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                            if encoded != last_payload:
                                self._safe_write(_event_stream_message(payload))
                                try:
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                                    return
                                last_payload = encoded
                            else:
                                self._safe_write(b": keepalive\n\n")
                                try:
                                    self.wfile.flush()
                                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                                    return
                            time.sleep(STREAM_INTERVAL_SECONDS)
                    if parsed.path == "/api/projects":
                        self._send_json(_dashboard_projects())
                        return
                    if parsed.path == "/api/mac-activity":
                        self._send_json(_mac_activity_payload())
                        return
                    if parsed.path == "/api/graph":
                        self._send_json(_graph_payload())
                        return
                    if parsed.path == "/api/tasks":
                        self._send_json(_tasks_payload())
                        return
                    if parsed.path == "/api/vps":
                        self._send_json(_vps_payload())
                        return
                    if parsed.path == "/api/status":
                        self._send_json(_dashboard_payload())
                        return
                    if parsed.path == "/api/operator":
                        self._send_json(operator_snapshot())
                        return
                    if parsed.path == "/style.css":
                        _serve_asset(self, FRONTEND_STYLE_PATH, "text/css; charset=utf-8")
                        return
                    if parsed.path == "/app.js":
                        _serve_asset(self, FRONTEND_APP_PATH, "application/javascript; charset=utf-8")
                        return
                    if parsed.path.startswith("/modules/"):
                        relative_path = parsed.path.removeprefix("/modules/")
                        asset_path = (FRONTEND_MODULES_ROOT / relative_path).resolve(strict=False)
                        if FRONTEND_MODULES_ROOT.resolve(strict=False) not in asset_path.parents and asset_path != FRONTEND_MODULES_ROOT.resolve(strict=False):
                            self._send_text("Not found", status=404)
                            return
                        _serve_asset(self, asset_path, "application/javascript; charset=utf-8")
                        return
                    if parsed.path.startswith("/vendor/"):
                        relative_path = parsed.path.removeprefix("/vendor/")
                        asset_path = (FRONTEND_VENDOR_ROOT / relative_path).resolve(strict=False)
                        if FRONTEND_VENDOR_ROOT.resolve(strict=False) not in asset_path.parents and asset_path != FRONTEND_VENDOR_ROOT.resolve(strict=False):
                            self._send_text("Not found", status=404)
                            return
                        content_type = "application/javascript; charset=utf-8"
                        _serve_asset(self, asset_path, content_type)
                        return
                    if parsed.path in {"/", "/index.html"}:
                        _write_dashboard()
                        body = DASHBOARD_PATH.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self._safe_write(body)
                        return
                    self._send_text("Not found", status=404)
                except Exception as exc:
                    self._send_text(f"Dashboard error: {exc}", status=500)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    if parsed.path == "/api/command":
                        payload = self._read_json_body()
                        action = " ".join(str(payload.get("action", "")).split()).strip().lower()
                        if action == "listen_once":
                            worker = threading.Thread(target=_dispatch_listen_once, daemon=True)
                            worker.start()
                            self._send_json(
                                {
                                    "status": "accepted",
                                    "action": action,
                                    "queued_at": _timestamp(),
                                },
                                status=202,
                            )
                            return
                        text = " ".join(str(payload.get("text", "")).split()).strip()
                        if not text:
                            self._send_json({"status": "error", "error": "Command text required."}, status=400)
                            return
                        worker = threading.Thread(target=_dispatch_command, args=(text,), daemon=True)
                        worker.start()
                        self._send_json(
                            {
                                "status": "accepted",
                                "text": text,
                                "queued_at": _timestamp(),
                            },
                            status=202,
                        )
                        return
                    if parsed.path == "/api/open_project":
                        name = parse_qs(parsed.query).get("name", [""])[0]
                        result = open_project(name)
                        status = 200 if result.get("status") == "ok" else 400
                        self._send_json(result, status=status)
                        return
                    self._send_text("Not found", status=404)
                except Exception as exc:
                    self._send_json({"status": "error", "error": str(exc)}, status=500)

            def log_message(self, format: str, *args) -> None:
                return

        try:
            PORT = _select_port(PREFERRED_PORT)
            _SERVER = ThreadingHTTPServer((HOST, PORT), Handler)
        except OSError as exc:
            print(f"[dashboard] could not start server: {exc}")
            _SERVER = None
            _SERVER_THREAD = None
            return None

        _SERVER_THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
        _SERVER_THREAD.start()
        _start_ws_server()
        _write_dashboard()
        return _SERVER


def show_dashboard_window(force: bool = False) -> None:
    global _LAST_WINDOW_OPENED_AT

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    url = dashboard_url()
    with _WINDOW_LOCK:
        now = time.monotonic()
        if not force and now - _LAST_WINDOW_OPENED_AT < 2.5:
            return
        _LAST_WINDOW_OPENED_AT = now

    if not _wait_for_dashboard_health(url):
        return

    if USE_NATIVE_HUD and _spawn_native_shell(url):
        return

    _open_browser_window(url)


def open_dashboard():
    """Generate + serve + open in a direct app-style window."""
    _write_dashboard()
    server = serve_dashboard()
    if server is not None:
        print(f"[Dashboard] Live HUD: {dashboard_url()}")
    show_dashboard_window(force=True)


if __name__ == "__main__":
    open_dashboard()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
