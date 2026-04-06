#!/usr/bin/env python3
"""Tool schema for Burry's tool-calling brain path.
All tools are registered via @tool decorator in brain/tools_registry.py.
"""
import brain.tools_registry  # noqa — triggers all @tool decorations

from brain.toolkit import get_toolkit


def get_tools_schema() -> list[dict]:
    return get_toolkit().get_tools()


TOOLS = get_tools_schema()
