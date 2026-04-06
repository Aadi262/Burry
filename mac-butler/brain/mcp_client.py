#!/usr/bin/env python3
"""AgentScope-compatible MCP client — wire any MCP server as a local Burry tool.
Burry can use ANY tool from the 200+ MCP ecosystem.

NOTE: agentscope.mcp unavailable due to local mcp/ module conflict.
This provides the same interface using direct HTTP calls to MCP servers.
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable

import httpx


async def get_mcp_tool(server_url: str, tool_name: str, transport: str = "streamable_http") -> Callable:
    """Get any MCP tool as a local Python callable.
    Usage: func = await get_mcp_tool('http://localhost:8000/mcp', 'search')
    """
    async def call_tool(**kwargs) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = {"tool": tool_name, "arguments": kwargs}
            resp = await client.post(f"{server_url}/call", json=payload)
            resp.raise_for_status()
            return str(resp.json().get("result", ""))
    call_tool.__name__ = tool_name
    call_tool.__doc__ = f"MCP tool: {tool_name} from {server_url}"
    return call_tool


async def list_mcp_tools(server_url: str) -> list[dict]:
    """List all available tools from an MCP server."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{server_url}/tools")
            resp.raise_for_status()
            return resp.json().get("tools", [])
    except Exception:
        return []


async def register_mcp_server(server_url: str, toolkit, transport: str = "streamable_http") -> list[str]:
    """Register ALL tools from an MCP server into Burry's toolkit.
    One MCP server URL = all its tools instantly available to Burry.
    """
    tools = await list_mcp_tools(server_url)
    registered = []
    for tool_info in tools:
        tool_name = tool_info.get("name", "")
        if not tool_name:
            continue
        try:
            func = await get_mcp_tool(server_url, tool_name, transport)
            toolkit.add(func)
            registered.append(tool_name)
        except Exception:
            pass
    return registered


# Pre-configured MCP servers Burry can use
MCP_SERVERS: dict[str, str] = {
    # Add your own MCP servers here:
    # "filesystem": "http://localhost:3001/mcp",
    # "github": "http://localhost:3002/mcp",
    # "slack": "http://localhost:3003/mcp",
}


def load_configured_mcp_servers(toolkit) -> None:
    """Load all configured MCP servers into toolkit at startup."""
    if not MCP_SERVERS:
        return
    for name, url in MCP_SERVERS.items():
        try:
            loop = asyncio.new_event_loop()
            registered = loop.run_until_complete(register_mcp_server(url, toolkit))
            loop.close()
            print(f"[MCP] Loaded {name}: {len(registered)} tools")
        except Exception as exc:
            print(f"[MCP] Failed to load {name}: {exc}")
