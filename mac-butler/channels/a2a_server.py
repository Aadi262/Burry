#!/usr/bin/env python3
"""A2A server — makes Burry discoverable by other AI agents.
Any A2A-compatible agent (Google ADK, AgentScope, CrewAI) can call Burry
as a specialized Mac operator agent.

Agent card:  http://localhost:3335/api/v1/agent-card
Run task:    POST http://localhost:3335/api/v1/run {"task": "open Cursor"}
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from capabilities import list_public_capabilities
from capabilities.contracts import CONTRACT_VERSION, ApiError, CommandRequest, CommandResult

A2A_PORT = 3335
API_BASE_PATH = "/api/v1"

def _api_path(path: str) -> str:
    return f"{API_BASE_PATH}/{str(path or '').strip('/')}"


def _agent_card() -> dict:
    descriptors = [descriptor.to_dict() for descriptor in list_public_capabilities()]
    return {
        "name": "Burry OS",
        "description": (
            "Local AI operator for macOS. Can control apps, run code, manage files, "
            "send messages, and interact with the Mac system."
        ),
        "version": "1.0",
        "capabilities": {
            "tools": descriptors,
            "tool_names": [item["tool_name"] for item in descriptors],
            "voice": True,
            "mac_control": True,
            "local_llm": True,
        },
        "endpoints": {
            "run": f"http://localhost:{A2A_PORT}{_api_path('run')}",
            "listen_once": f"http://localhost:{A2A_PORT}{_api_path('listen_once')}",
            "interrupt": f"http://localhost:{A2A_PORT}{_api_path('interrupt')}",
            "agent_card": f"http://localhost:{A2A_PORT}{_api_path('agent-card')}",
            "health": f"http://localhost:{A2A_PORT}{_api_path('health')}",
        },
        "contract_version": CONTRACT_VERSION,
    }


class A2AHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == _api_path("agent-card"):
            body = json.dumps(_agent_card()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == _api_path("health"):
            body = json.dumps(
                {
                    "ok": True,
                    "port": A2A_PORT,
                    "agent": "Burry OS",
                    "api_version": "v1",
                    "contract_version": CONTRACT_VERSION,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json(ApiError(error="Not found", status=404, code="not_found").to_dict(), status=404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except Exception:
            length = 0
        try:
            raw = self.rfile.read(length) if length > 0 else b"{}"
            body = json.loads(raw.decode() or "{}")
        except Exception:
            body = {}
        request = CommandRequest.from_dict(body)
        path = urlparse(self.path).path

        if path == _api_path("run"):
            task = str(request.text or body.get("task", "")).strip()
            if not task:
                self._send_json(CommandResult(status="error", error="No task provided").to_dict(), status=400)
                return
            worker = threading.Thread(target=_run_task, args=(task,), daemon=True, name="burry-a2a-run")
            worker.start()
            self._send_json(
                CommandResult(
                    status="accepted",
                    message="task accepted",
                    data={"agent": "Burry OS", "task": task},
                ).to_dict(),
                status=202,
            )
            return

        if path == _api_path("listen_once"):
            timeout = request.timeout if request.timeout is not None else body.get("timeout", 10.0)
            worker = threading.Thread(
                target=_listen_once_worker,
                args=(timeout,),
                daemon=True,
                name="burry-a2a-listen",
            )
            worker.start()
            self._send_json(
                CommandResult(
                    status="accepted",
                    message="listen_once accepted",
                    data={"action": "listen_once", "timeout": float(timeout or 10.0)},
                ).to_dict(),
                status=202,
            )
            return

        if path == _api_path("interrupt"):
            text = str(request.text or "").strip()
            if not text:
                self._send_json(CommandResult(status="error", error="No interrupt text provided").to_dict(), status=400)
                return
            try:
                from butler import interrupt_burry

                interrupt_burry(text)
                self._send_json(
                    CommandResult(
                        status="interrupted",
                        message="interrupt delivered",
                        data={"text": text},
                    ).to_dict(),
                    status=200,
                )
            except Exception as exc:
                self._send_json(CommandResult(status="error", error=str(exc)).to_dict(), status=500)
            return

        self._send_json(ApiError(error="Not found", status=404, code="not_found").to_dict(), status=404)

    def log_message(self, *args):
        pass  # Suppress access logs

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run_task(task: str) -> None:
    try:
        from butler import handle_input

        handle_input(task, test_mode=False)
    except Exception as exc:
        print(f"[A2A] run task failed: {exc}")


def _listen_once_worker(timeout: float = 10.0) -> None:
    try:
        from butler import handle_input
        from voice.stt import listen_for_command

        heard = " ".join(str(listen_for_command(timeout=float(timeout or 10.0)) or "").split()).strip()
        if heard:
            handle_input(heard, test_mode=False)
    except Exception as exc:
        print(f"[A2A] listen_once failed: {exc}")


def start_custom_a2a_server() -> None:
    """Start the fallback custom A2A server in a background thread."""
    server = ThreadingHTTPServer(("localhost", A2A_PORT), A2AHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="burry-a2a")
    thread.start()
    print(f"[A2A] Burry is discoverable at http://localhost:{A2A_PORT}{API_BASE_PATH}/agent-card")


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
