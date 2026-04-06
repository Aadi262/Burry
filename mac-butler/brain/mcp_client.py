#!/usr/bin/env python3
"""AgentScope MCP client helpers for Burry.

This module now uses AgentScope's real MCP clients instead of the earlier
HTTP-only compatibility shim.
"""
from __future__ import annotations

import asyncio
from typing import Any

from agentscope.mcp import HttpStatelessClient, StdIOStatefulClient

from butler_config import MCP_SERVERS


def _resolve_agentscope_toolkit(toolkit):
    if hasattr(toolkit, "as_agentscope"):
        return toolkit.as_agentscope()
    return toolkit


def _enabled_server_configs() -> list[tuple[str, dict[str, Any]]]:
    enabled: list[tuple[str, dict[str, Any]]] = []
    for server_name, config in sorted((MCP_SERVERS or {}).items()):
        current = dict(config or {})
        if not current.get("enabled"):
            continue
        enabled.append((server_name, current))
    return enabled


def _build_client(server_name: str, config: dict[str, Any]):
    transport = str(config.get("transport", "stdio") or "stdio").strip().lower()
    if transport == "stdio":
        command = list(config.get("command") or [])
        if not command:
            raise ValueError(f"MCP server '{server_name}' is missing a command")
        return StdIOStatefulClient(
            name=server_name,
            command=str(command[0]),
            args=[str(item) for item in command[1:]],
            env={str(k): str(v) for k, v in dict(config.get("env") or {}).items()},
            cwd=str(config.get("cwd", "") or None) or None,
        )

    url = str(config.get("url") or config.get("server_url") or "").strip()
    if not url:
        raise ValueError(f"MCP server '{server_name}' is missing a URL")
    if transport not in {"streamable_http", "sse"}:
        raise ValueError(f"Unsupported MCP transport for '{server_name}': {transport}")
    return HttpStatelessClient(
        name=server_name,
        transport=transport,
        url=url,
        headers={str(k): str(v) for k, v in dict(config.get("headers") or {}).items()} or None,
        timeout=float(config.get("timeout", 30) or 30),
    )


async def get_mcp_tool(server_url: str, tool_name: str, transport: str = "streamable_http"):
    """Return one MCP tool as a local callable AgentScope function."""
    client = HttpStatelessClient(
        name=f"mcp_{tool_name}",
        transport=transport,
        url=server_url,
    )
    return await client.get_callable_function(func_name=tool_name)


async def register_mcp_server(server_url: str, toolkit, transport: str = "streamable_http") -> list[str]:
    """Register all tools from one HTTP MCP server into a toolkit."""
    resolved_toolkit = _resolve_agentscope_toolkit(toolkit)
    client = HttpStatelessClient(
        name=f"mcp_{transport}",
        transport=transport,
        url=server_url,
    )
    tools = await client.list_tools()
    await resolved_toolkit.register_mcp_client(client)
    return [str(tool.name) for tool in tools]


async def _load_server(server_name: str, config: dict[str, Any], toolkit) -> list[str]:
    resolved_toolkit = _resolve_agentscope_toolkit(toolkit)
    client = _build_client(server_name, config)
    tools = await client.list_tools()
    await resolved_toolkit.register_mcp_client(client, namesake_strategy="override")
    return [str(tool.name) for tool in tools]


def load_configured_mcp_servers(toolkit) -> None:
    """Load enabled MCP servers from butler_config into the shared toolkit."""
    enabled = _enabled_server_configs()
    if not enabled:
        return

    async def _runner() -> None:
        for server_name, config in enabled:
            try:
                registered = await _load_server(server_name, config, toolkit)
                print(f"[MCP] Loaded {server_name}: {len(registered)} tools")
            except Exception as exc:
                print(f"[MCP] Failed to load {server_name}: {exc}")

    asyncio.run(_runner())
