#!/usr/bin/env python3
"""Project dashboard generator and tiny local server."""

from __future__ import annotations

import json
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from .github_sync import get_github_context
    from .open_project import open_project
    from .project_store import load_projects
except ImportError:
    from github_sync import get_github_context
    from open_project import open_project
    from project_store import load_projects

ROOT = Path(__file__).resolve().parent
DASHBOARD_PATH = ROOT / "dashboard.html"
HOST = "127.0.0.1"
PORT = 3333
_SERVER: ThreadingHTTPServer | None = None
_SERVER_THREAD: threading.Thread | None = None
_SERVER_LOCK = threading.Lock()


def _status_rank(status: str) -> int:
    return {"active": 0, "paused": 1, "done": 2}.get(status, 9)


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generate_dashboard() -> str:
    """Returns HTML string."""
    projects = load_projects()
    payload = json.dumps(projects)
    github_context = get_github_context()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Burry OS</title>
  <style>
    :root {{
      --bg: #0d0d0d;
      --panel: rgba(255, 255, 255, 0.05);
      --panel-border: rgba(255, 255, 255, 0.1);
      --text: #f5f7fb;
      --muted: #96a0ae;
      --accent: #61f0c2;
      --accent-2: #49a5ff;
      --danger: #ff6b6b;
      --warning: #ffbd59;
      --done: #7ddc86;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "SF Pro Display", "Helvetica Neue", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(73,165,255,0.18), transparent 32%),
        radial-gradient(circle at top right, rgba(97,240,194,0.16), transparent 28%),
        linear-gradient(180deg, #0d0d0d 0%, #111418 100%);
      padding: 28px;
    }}
    .shell {{
      max-width: 1400px;
      margin: 0 auto;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      margin-bottom: 24px;
    }}
    .brand {{
      letter-spacing: 0.24em;
      font-size: 14px;
      color: var(--accent);
      text-transform: uppercase;
    }}
    .title {{
      font-size: clamp(36px, 6vw, 78px);
      font-weight: 700;
      margin: 8px 0 0;
      line-height: 0.95;
      text-shadow: 0 0 32px rgba(97,240,194,0.18);
    }}
    .stamp {{
      color: var(--muted);
      font-size: 14px;
      text-align: right;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }}
    .card, .actions {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 22px;
      backdrop-filter: blur(16px);
      box-shadow: 0 20px 48px rgba(0, 0, 0, 0.28);
    }}
    .card {{
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      min-height: 320px;
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }}
    .card-name {{
      font-size: 28px;
      font-weight: 700;
      line-height: 1;
    }}
    .badge {{
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid rgba(255, 255, 255, 0.14);
      white-space: nowrap;
    }}
    .badge.active {{ color: var(--accent); background: rgba(97,240,194,0.08); }}
    .badge.paused {{ color: var(--warning); background: rgba(255,189,89,0.08); }}
    .badge.done {{ color: var(--done); background: rgba(125,220,134,0.08); }}
    .badge.healthy {{ color: var(--done); background: rgba(125,220,134,0.08); }}
    .badge.degraded {{ color: var(--warning); background: rgba(255,189,89,0.08); }}
    .badge.offline {{ color: var(--danger); background: rgba(255,107,107,0.08); }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .live {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .dot {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #4a4a4a;
      box-shadow: 0 0 0 0 transparent;
    }}
    .dot.live {{
      background: var(--done);
      box-shadow: 0 0 14px rgba(125,220,134,0.8);
    }}
    .progress {{
      position: relative;
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      overflow: hidden;
    }}
    .progress > span {{
      position: absolute;
      inset: 0 auto 0 0;
      width: 0;
      background: linear-gradient(90deg, var(--accent-2), var(--accent));
      border-radius: inherit;
      box-shadow: 0 0 18px rgba(73,165,255,0.45);
    }}
    .section-title {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.14em;
    }}
    .list {{
      margin: 0;
      padding-left: 18px;
      color: var(--text);
    }}
    .list li {{
      margin-bottom: 6px;
      line-height: 1.35;
    }}
    .blockers li {{
      color: var(--danger);
    }}
    .open-btn {{
      margin-top: auto;
      width: 100%;
      border: 0;
      border-radius: 14px;
      padding: 14px 16px;
      background: linear-gradient(90deg, rgba(73,165,255,0.95), rgba(97,240,194,0.95));
      color: #041019;
      font-weight: 700;
      cursor: pointer;
      transition: transform 120ms ease, box-shadow 120ms ease;
      box-shadow: 0 12px 28px rgba(73,165,255,0.25);
    }}
    .open-btn:hover {{
      transform: translateY(-1px);
      box-shadow: 0 16px 30px rgba(73,165,255,0.32);
    }}
    .actions {{
      margin-top: 22px;
      padding: 20px;
    }}
    .actions-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .action-item {{
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,0.03);
    }}
    .action-item strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 15px;
    }}
    .github {{
      margin-top: 12px;
      font-size: 12px;
      color: var(--muted);
    }}
    @media (max-width: 1100px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 760px) {{
      body {{ padding: 18px; }}
      .topbar {{ flex-direction: column; align-items: flex-start; }}
      .stamp {{ text-align: left; }}
      .grid, .actions-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div>
        <div class="brand">BURRY OS</div>
        <div class="title">Project Command Center</div>
      </div>
      <div class="stamp">
        <div>Last updated</div>
        <strong id="last-updated">{_timestamp()}</strong>
      </div>
    </div>

    <section class="grid" id="project-grid"></section>

    <section class="actions">
      <div class="section-title">Next Actions</div>
      <div class="actions-grid" id="next-actions"></div>
      <div class="github">{github_context or 'GitHub sync not populated yet.'}</div>
    </section>
  </div>

  <script>
    const initialProjects = {payload};

    function sortProjects(projects) {{
      return [...projects].sort((a, b) => {{
        const rank = {{ active: 0, paused: 1, done: 2 }};
        const rankA = rank[a.status] ?? 9;
        const rankB = rank[b.status] ?? 9;
        if (rankA !== rankB) return rankA - rankB;
        return (b.completion ?? 0) - (a.completion ?? 0);
      }});
    }}

    function renderProjects(projects) {{
      const grid = document.getElementById("project-grid");
      grid.innerHTML = "";

      for (const project of sortProjects(projects)) {{
        const blockers = Array.isArray(project.blockers) ? project.blockers : [];
        const tasks = Array.isArray(project.next_tasks) ? project.next_tasks.slice(0, 2) : [];
        const card = document.createElement("article");
        card.className = "card";
        card.innerHTML = `
          <div class="card-head">
            <div class="card-name">${{project.name}}</div>
            <div class="badge ${{project.status || "paused"}}">${{project.status || "paused"}}</div>
          </div>
          <div class="meta">
            <span>${{project.completion ?? 0}}% estimated</span>
            <span class="live"><span class="dot ${{project.live ? "live" : ""}}"></span>${{project.deploy_target || "No deploy target"}}</span>
          </div>
          <div class="progress"><span style="width: ${{project.completion ?? 0}}%"></span></div>
          <div class="meta">
            <span>Basis: ${{project.completion_basis || "registry"}}</span>
            <span>Signals: ${{project.status_files_found ?? 0}}/${{project.status_files_total ?? 0}}</span>
          </div>
          <div class="meta">
            <span>Last commit: ${{project.last_commit ? String(project.last_commit).slice(0, 10) : "unknown"}}</span>
            <span>Open issues: ${{project.open_issues ?? 0}}</span>
          </div>
          <div class="meta">
            <span>Health: <span class="badge ${{project.health_status || "degraded"}}">${{project.health_status || "degraded"}}</span> ${{project.health_signals_ok ?? 0}}/${{project.health_signals_total ?? 0}}</span>
            <span>Verify: ${{project.last_test_status || "unknown"}}</span>
          </div>
          <div class="meta">
            <span>Git: ${{project.git_branch || "no git"}}${{project.git_dirty === true ? " dirty" : project.git_dirty === false ? " clean" : ""}}</span>
            <span>${{project.last_verified_at ? ("Verified " + String(project.last_verified_at).slice(0, 16).replace("T", " ")) : "No verification yet"}}</span>
          </div>
          <div>
            <div class="section-title">Blockers</div>
            <ul class="list blockers">
              ${{
                blockers.length
                  ? blockers.map((item) => `<li>${{item}}</li>`).join("")
                  : "<li style='color: var(--done)'>No blockers logged.</li>"
              }}
            </ul>
          </div>
          <div>
            <div class="section-title">Next Tasks</div>
            <ul class="list">
              ${{
                tasks.length
                  ? tasks.map((item) => `<li>${{item}}</li>`).join("")
                  : "<li>No tasks queued.</li>"
              }}
            </ul>
          </div>
          <button class="open-btn" data-project="${{project.name}}">Open Project</button>
        `;
        grid.appendChild(card);
      }}

      for (const button of document.querySelectorAll(".open-btn")) {{
        button.addEventListener("click", async (event) => {{
          const name = event.currentTarget.getAttribute("data-project");
          await fetch(`/api/open_project?name=${{encodeURIComponent(name)}}`, {{ method: "POST" }});
        }});
      }}
    }}

    function renderNextActions(projects) {{
      const mount = document.getElementById("next-actions");
      mount.innerHTML = "";
      const items = [];
      for (const project of sortProjects(projects)) {{
        for (const task of (project.next_tasks || []).slice(0, 2)) {{
          items.push({{ project: project.name, status: project.status, task }});
        }}
      }}
      for (const item of items) {{
        const node = document.createElement("div");
        node.className = "action-item";
        node.innerHTML = `<strong>${{item.project}}</strong><span>${{item.task}}</span>`;
        mount.appendChild(node);
      }}
    }}

    async function refresh() {{
      try {{
        const response = await fetch("/api/projects");
        const projects = await response.json();
        renderProjects(projects);
        renderNextActions(projects);
        document.getElementById("last-updated").textContent = new Date().toLocaleString();
      }} catch (error) {{
        console.error(error);
      }}
    }}

    renderProjects(initialProjects);
    renderNextActions(initialProjects);
    setInterval(refresh, 60000);
  </script>
</body>
</html>
"""


def _write_dashboard() -> None:
    DASHBOARD_PATH.write_text(generate_dashboard(), encoding="utf-8")


def serve_dashboard():
    """
    Starts a simple HTTP server on localhost:3333.
    GET /api/projects → returns projects.json as JSON
    GET / → serves dashboard.html
    Runs in background thread so it doesn't block Butler.
    """

    global _SERVER, _SERVER_THREAD
    _write_dashboard()

    with _SERVER_LOCK:
        if _SERVER is not None and _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
            return _SERVER

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, payload: dict | list, status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/projects":
                    self._send_json(load_projects())
                    return
                if parsed.path in {"/", "/index.html"}:
                    _write_dashboard()
                    body = DASHBOARD_PATH.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/open_project":
                    name = parse_qs(parsed.query).get("name", [""])[0]
                    result = open_project(name)
                    status = 200 if result.get("status") == "ok" else 400
                    self._send_json(result, status=status)
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args) -> None:
                return

        try:
            _SERVER = ThreadingHTTPServer((HOST, PORT), Handler)
        except OSError as exc:
            print(f"[dashboard] could not start server: {exc}")
            _SERVER = None
            _SERVER_THREAD = None
            return None

        _SERVER_THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
        _SERVER_THREAD.start()
        return _SERVER


def open_dashboard():
    """Generate + serve + open in browser."""
    _write_dashboard()
    serve_dashboard()
    try:
        webbrowser.open(f"http://{HOST}:{PORT}")
    except Exception:
        pass


if __name__ == "__main__":
    open_dashboard()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
