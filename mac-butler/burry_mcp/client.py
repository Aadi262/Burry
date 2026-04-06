#!/usr/bin/env python3
"""
mcp/client.py
Minimal stdio MCP client for optional Brave/GitHub integrations.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import threading
from itertools import count
from typing import Any

from butler_config import MCP_SERVERS, SEARCH_BACKEND
from butler_secrets.loader import get_mcp_secret

CLIENT_INFO = {"name": "mac-butler", "version": "1.0"}
PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    """Raised when an MCP server cannot be reached or returns an error."""


def _merge_server_config(server_name: str) -> dict:
    base = dict(MCP_SERVERS.get(server_name, {}))
    secret = get_mcp_secret(server_name)
    if secret:
        if "enabled" in secret:
            base["enabled"] = secret["enabled"]
        if secret.get("command"):
            base["command"] = secret["command"]
        env = dict(base.get("env", {}))
        env.update(secret.get("env", {}))
        base["env"] = env
    return base


def get_server_status(server_name: str) -> dict:
    config = _merge_server_config(server_name)
    command = config.get("command") or []
    enabled = bool(config.get("enabled"))
    env_map = config.get("env", {})
    missing_env = [
        name
        for name, value in env_map.items()
        if not (value or os.environ.get(name))
    ]
    return {
        "name": server_name,
        "enabled": enabled,
        "configured": bool(command),
        "command": command,
        "missing_env": missing_env,
        "ready": enabled and bool(command) and not missing_env,
    }


def describe_servers() -> list[str]:
    lines = []
    for server_name in sorted(MCP_SERVERS):
        status = get_server_status(server_name)
        if status["ready"]:
            lines.append(f"{server_name}: ready")
        elif status["enabled"] and status["configured"]:
            missing = ", ".join(status["missing_env"]) or "runtime"
            lines.append(f"{server_name}: needs {missing}")
        elif status["configured"]:
            lines.append(f"{server_name}: configured but disabled")
    return lines


class StdioMCPClient:
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.config = _merge_server_config(server_name)
        self.process: subprocess.Popen[bytes] | None = None
        self._ids = count(1)
        self._stderr: list[str] = []

    def __enter__(self) -> "StdioMCPClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        status = get_server_status(self.server_name)
        if not status["ready"]:
            raise MCPError(f"{self.server_name} MCP not ready: {status}")

        env = os.environ.copy()
        for key, value in self.config.get("env", {}).items():
            if value:
                env[key] = value

        command = self.config["command"]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        if not self.process:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
        except Exception:
            pass
        try:
            self.process.terminate()
            self.process.wait(timeout=2)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        finally:
            self.process = None

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        return result.get("tools", []) if isinstance(result, dict) else []

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        result = self._request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
        return result if isinstance(result, dict) else {"content": []}

    def _notify(self, method: str, params: dict) -> None:
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        self._send(message)

    def _request(self, method: str, params: dict) -> Any:
        request_id = next(self._ids)
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._send(message)
        while True:
            response = self._read_message()
            if response.get("id") != request_id:
                continue
            if response.get("error"):
                raise MCPError(str(response["error"]))
            return response.get("result", {})

    def _send(self, payload: dict) -> None:
        if not self.process or not self.process.stdin:
            raise MCPError(f"{self.server_name} MCP process is not running")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header + body)
        self.process.stdin.flush()

    def _read_message(self) -> dict:
        if not self.process or not self.process.stdout:
            raise MCPError(f"{self.server_name} MCP process is not running")
        header_blob = self._read_until(b"\r\n\r\n")
        headers = {}
        for line in header_blob.decode("utf-8", errors="ignore").split("\r\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            raise MCPError(f"{self.server_name} MCP sent invalid content length")
        body = self._read_exact(length)
        return json.loads(body.decode("utf-8"))

    def _read_until(self, marker: bytes, timeout: float = 20.0) -> bytes:
        buffer = bytearray()
        while marker not in buffer:
            buffer.extend(self._read_exact(1, timeout=timeout))
        return bytes(buffer)

    def _read_exact(self, size: int, timeout: float = 20.0) -> bytes:
        if not self.process or not self.process.stdout:
            raise MCPError(f"{self.server_name} MCP process is not running")
        fd = self.process.stdout.fileno()
        chunks = bytearray()
        while len(chunks) < size:
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                stderr_tail = " ".join(self._stderr[-3:]).strip()
                raise MCPError(
                    f"{self.server_name} MCP timed out"
                    + (f" ({stderr_tail})" if stderr_tail else "")
                )
            chunk = os.read(fd, size - len(chunks))
            if not chunk:
                stderr_tail = " ".join(self._stderr[-3:]).strip()
                raise MCPError(
                    f"{self.server_name} MCP closed the stream"
                    + (f" ({stderr_tail})" if stderr_tail else "")
                )
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return
        while True:
            line = self.process.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="ignore").strip()
            if text:
                self._stderr.append(text)
                self._stderr = self._stderr[-20:]


def list_server_tools(server_name: str) -> list[dict]:
    with StdioMCPClient(server_name) as client:
        return client.list_tools()


def normalize_tool_result(result: dict) -> str:
    parts: list[str] = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            text = str(item.get("text", "")).strip()
            if text:
                parts.append(text)
    structured = result.get("structuredContent")
    if structured:
        try:
            parts.append(json.dumps(structured, indent=2))
        except TypeError:
            parts.append(str(structured))
    return "\n".join(parts).strip()


def _score_tool(tool: dict, hints: list[str]) -> int:
    haystack = " ".join(
        [
            str(tool.get("name", "")),
            str(tool.get("description", "")),
        ]
    ).lower()
    return sum(1 for hint in hints if hint in haystack)


def _pick_tool(server_name: str, hints: list[str]) -> dict:
    tools = list_server_tools(server_name)
    if not tools:
        raise MCPError(f"{server_name} MCP exposed no tools")
    ranked = sorted(tools, key=lambda tool: _score_tool(tool, hints), reverse=True)
    return ranked[0]


def _fit_arguments(schema: dict, arguments: dict) -> dict:
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not properties:
        return dict(arguments)

    aliases = {
        "query": ["query", "q", "search", "term", "input", "text"],
        "count": ["count", "limit", "n", "num_results", "numResults", "page_size"],
        "repo": ["repo", "repository", "repo_name", "name"],
        "owner": ["owner", "org", "organization"],
    }

    fitted = {}
    for key, value in arguments.items():
        if key in properties:
            fitted[key] = value
            continue
        for canonical, names in aliases.items():
            if key != canonical:
                continue
            for candidate in names:
                if candidate in properties:
                    fitted[candidate] = value
                    break
    return fitted


def call_server_tool(
    server_name: str,
    arguments: dict | None = None,
    preferred_tool: str | None = None,
    hints: list[str] | None = None,
) -> dict:
    hints = hints or []
    with StdioMCPClient(server_name) as client:
        tools = client.list_tools()
        if preferred_tool:
            tool = next(
                (item for item in tools if item.get("name") == preferred_tool),
                None,
            )
        else:
            tool = None
        if tool is None:
            if not tools:
                raise MCPError(f"{server_name} MCP exposed no tools")
            if hints:
                tool = sorted(tools, key=lambda item: _score_tool(item, hints), reverse=True)[0]
            else:
                tool = tools[0]

        schema = tool.get("inputSchema", {}) if isinstance(tool, dict) else {}
        fitted_args = _fit_arguments(schema, arguments or {})
        result = client.call_tool(tool["name"], fitted_args)
        result["tool_name"] = tool["name"]
        return result


def search_web(query: str, count: int = 5) -> dict:
    if SEARCH_BACKEND not in {"auto", "mcp"}:
        return {"backend": "disabled", "text": "", "tool": ""}

    status = get_server_status("brave")
    if not status["ready"]:
        return {"backend": "disabled", "text": "", "tool": ""}

    result = call_server_tool(
        "brave",
        arguments={"query": query, "count": count},
        hints=["search", "web", "brave"],
    )
    return {
        "backend": "brave_mcp",
        "tool": result.get("tool_name", ""),
        "text": normalize_tool_result(result),
    }
