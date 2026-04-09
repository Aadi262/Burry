"""Typed contracts for semantic planning and capability execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

TaskKind = Literal["answer", "control", "lookup", "draft", "plan", "clarify"]
TurnStage = Literal["accepted", "progress", "final"]
ActionBuilder = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    action_type: str
    kind: TaskKind
    description: str
    required_args: tuple[str, ...] = ()
    latency_budget_s: float = 5.0
    confirmation_required: bool = False
    sync_execution: bool = False
    quick_response: str = ""
    action_builder: ActionBuilder | None = None
    default_args: dict[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()


@dataclass(slots=True)
class CapabilityTask:
    kind: TaskKind
    goal: str
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    answer: str = ""
    needs_clarification: bool = False
    clarification: str = ""
    confidence: float = 0.0
    source: str = "semantic_planner"
    intent_name: str = ""
    quick_response: str = ""
    force_override: bool = False


@dataclass(slots=True)
class TurnEvent:
    stage: TurnStage
    speech: str = ""
    tool: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
