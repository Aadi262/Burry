#!/usr/bin/env python3
"""Burry Toolkit — single source of truth for all Burry tools.
AgentScope-compatible Toolkit pattern without the import conflict.
Adding a new tool = one decorated function. Zero other file changes.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable


class Toolkit:
    """Registry of callable tools with OpenAI-style schema generation."""

    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def add(self, func: Callable) -> None:
        """Register a function as a Burry tool."""
        self._tools[func.__name__] = func

    def call(self, name: str, **kwargs) -> Any:
        """Call a registered tool by name."""
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return self._tools[name](**kwargs)

    def get_tools(self) -> list[dict]:
        """Return OpenAI-style tool schema for all registered tools."""
        schemas = []
        for name, func in self._tools.items():
            schemas.append(self._build_schema(name, func))
        return schemas

    def _build_schema(self, name: str, func: Callable) -> dict:
        sig = inspect.signature(func)
        doc = (func.__doc__ or "").strip()
        properties = {}
        required = []
        hints = getattr(func, "__annotations__", {})
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            ptype = hints.get(param_name)
            json_type = "string"
            if ptype in (int,):
                json_type = "integer"
            elif ptype in (float,):
                json_type = "number"
            elif ptype in (bool,):
                json_type = "boolean"
            properties[param_name] = {"type": json_type}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": doc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


_toolkit = Toolkit()


def get_toolkit() -> Toolkit:
    return _toolkit


def tool(func: Callable) -> Callable:
    """Decorator that registers a function as a Burry tool."""
    _toolkit.add(func)
    return func
