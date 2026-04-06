#!/usr/bin/env python3
"""
context/mcp_context.py
Lightweight MCP availability context for Butler prompts.
"""

from butler_config import MCP_CONTEXT_ENABLED
from burry_mcp import describe_servers


def get_mcp_context() -> str:
    if not MCP_CONTEXT_ENABLED:
        return ""
    lines = describe_servers()
    if not lines:
        return ""
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_mcp_context() or "No MCP servers configured")
