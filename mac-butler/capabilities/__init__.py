"""Capability-driven planning surface for Butler."""

from .contracts import (
    CONTRACT_VERSION,
    ApiError,
    ApiResponse,
    CapabilityDescriptor,
    CapabilityTask,
    ClassifierResult,
    CommandRequest,
    CommandResult,
    HudEventEnvelope,
    PendingState,
    ToolInvocation,
    ToolResult,
    ToolSpec,
    TurnEvent,
    contract_timestamp,
)
from .planner import looks_like_current_role_lookup, plan_semantic_task
from .registry import (
    TOOL_SPECS,
    build_action,
    get_capability_descriptor,
    get_tool_spec,
    list_public_capabilities,
    tool_catalog_for_prompt,
)

__all__ = [
    "CONTRACT_VERSION",
    "ApiError",
    "ApiResponse",
    "CapabilityDescriptor",
    "CapabilityTask",
    "ClassifierResult",
    "CommandRequest",
    "CommandResult",
    "HudEventEnvelope",
    "PendingState",
    "TOOL_SPECS",
    "ToolInvocation",
    "ToolResult",
    "ToolSpec",
    "TurnEvent",
    "build_action",
    "contract_timestamp",
    "get_capability_descriptor",
    "get_tool_spec",
    "list_public_capabilities",
    "looks_like_current_role_lookup",
    "plan_semantic_task",
    "tool_catalog_for_prompt",
]
