#!/usr/bin/env python3
"""A2A server — makes Burry discoverable by other AI agents.
Any A2A-compatible agent (Google ADK, AgentScope, CrewAI) can call Burry
as a specialized Mac operator agent.

Agent card:  http://localhost:3335/agent-card
Run task:    POST http://localhost:3335/run {"task": "open Cursor"}
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

A2A_PORT = 3335

AGENT_CARD = {
    "name": "Burry OS",
    "description": (
        "Local AI operator for macOS. Can control apps, run code, manage files, "
        "send messages, and interact with the Mac system."
    ),
    "version": "1.0",
    "capabilities": {
        "tools": [
            "open_project", "focus_app", "run_shell", "send_email",
            "spotify_control", "git_commit", "browse_web", "deep_research",
            "plan_and_execute", "search_knowledge_base",
        ],
        "voice": True,
        "mac_control": True,
        "local_llm": True,
    },
    "endpoints": {
        "run": f"http://localhost:{A2A_PORT}/run",
        "agent_card": f"http://localhost:{A2A_PORT}/agent-card",
    },
}


class A2AHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/agent-card":
            body = json.dumps(AGENT_CARD).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode())
            task = body.get("task", "") or body.get("text", "")

            if task:
                try:
                    from butler import handle_input
                    handle_input(task, test_mode=False)
                    response = {"status": "ok", "agent": "Burry OS", "task": task}
                except Exception as exc:
                    response = {"status": "error", "error": str(exc)}
            else:
                response = {"status": "error", "message": "No task provided"}

            body_bytes = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Suppress access logs


def start_custom_a2a_server() -> None:
    """Start the fallback custom A2A server in a background thread."""
    server = HTTPServer(("localhost", A2A_PORT), A2AHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="burry-a2a")
    thread.start()
    print(f"[A2A] Burry is discoverable at http://localhost:{A2A_PORT}/agent-card")


def start_agentscope_a2a(agent=None) -> bool:
    """Start AgentScope native A2A when available, else fall back to custom A2A."""
    try:
        # TODO: Switch this path to the native AgentScope service once the
        # installed agentscope package includes agentscope.server.AgentService.
        from agentscope.server import AgentService

        if agent is None:
            from brain.agentscope_backbone import get_backbone

            backbone = get_backbone()
            agent = getattr(backbone, "agent", None)
        if agent is None:
            return False
        service = AgentService(agent=agent, host="localhost", port=3335)
        threading.Thread(
            target=service.run,
            daemon=True,
            name="burry-a2a-agentscope",
        ).start()
        print("[A2A] AgentScope native A2A at http://localhost:3335")
        return True
    except (ImportError, Exception) as exc:
        print(f"[A2A] AgentScope A2A not available: {exc}")
        try:
            start_custom_a2a_server()
        except Exception as fallback_exc:
            print(f"[A2A] Custom A2A fallback failed: {fallback_exc}")
        return False


def start_a2a_server() -> None:
    """Backward-compatible entrypoint for the custom A2A server."""
    start_custom_a2a_server()
