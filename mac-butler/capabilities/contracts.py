"""Typed contracts for semantic planning, transport, and capability execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Literal

CONTRACT_VERSION = "1.0"

TaskKind = Literal["answer", "control", "lookup", "draft", "plan", "clarify"]
TurnStage = Literal["accepted", "progress", "final"]
CommandStatus = Literal["accepted", "queued", "acknowledged", "executing", "ok", "error", "interrupted"]
ActionBuilder = Callable[[dict[str, Any]], dict[str, Any]]
JsonPayload = dict[str, Any] | list[Any]


def contract_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


@dataclass(slots=True)
class ToolSpec:
    name: str
    action_type: str
    kind: TaskKind
    description: str
    capability_id: str = ""
    required_args: tuple[str, ...] = ()
    latency_budget_s: float = 5.0
    confirmation_required: bool = False
    sync_execution: bool = False
    public: bool = False
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "speech": self.speech,
            "tool": self.tool,
            "payload": dict(self.payload),
        }


@dataclass(slots=True)
class ApiResponse:
    kind: str
    data: JsonPayload = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "kind": _text(self.kind) or "response",
            "data": self.data if isinstance(self.data, (dict, list)) else {},
        }


@dataclass(slots=True)
class ApiError:
    error: str
    status: int = 500
    kind: str = "error"
    code: str = ""
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "kind": _text(self.kind) or "error",
            "error": _text(self.error) or "Unknown error",
            "status": int(self.status or 500),
        }
        if self.code:
            payload["code"] = _text(self.code)
        return payload


@dataclass(slots=True)
class CommandRequest:
    text: str = ""
    action: str = ""
    source: str = "unknown"
    timeout: float | None = None
    session_id: str = ""
    request_id: str = ""
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "CommandRequest":
        data = payload if isinstance(payload, dict) else {}
        timeout_raw = data.get("timeout")
        try:
            timeout = float(timeout_raw) if timeout_raw not in {None, ""} else None
        except Exception:
            timeout = None
        return cls(
            text=_text(data.get("text", "")),
            action=_text(data.get("action", "")),
            source=_text(data.get("source", "")) or "unknown",
            timeout=timeout,
            session_id=_text(data.get("session_id", "")),
            request_id=_text(data.get("request_id", "")),
            contract_version=_text(data.get("contract_version", "")) or CONTRACT_VERSION,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "text": self.text,
            "action": self.action,
            "source": self.source,
        }
        if self.timeout is not None:
            payload["timeout"] = float(self.timeout)
        if self.session_id:
            payload["session_id"] = self.session_id
        if self.request_id:
            payload["request_id"] = self.request_id
        return payload


@dataclass(slots=True)
class CommandResult:
    status: CommandStatus
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    request_id: str = ""
    session_id: str = ""
    contract_version: str = CONTRACT_VERSION

    def to_dict(self, *, include_legacy_fields: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "status": self.status,
            "message": self.message,
            "data": dict(self.data),
        }
        if include_legacy_fields:
            payload.update(self.data)
        if self.error:
            payload["error"] = self.error
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.session_id:
            payload["session_id"] = self.session_id
        return payload


@dataclass(slots=True)
class ToolInvocation:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    capability_id: str = ""
    source: str = ""
    confirmation_required: bool = False
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "tool": self.tool,
            "args": dict(self.args),
            "capability_id": self.capability_id,
            "source": self.source,
            "confirmation_required": self.confirmation_required,
        }


@dataclass(slots=True)
class ToolResult:
    tool: str
    status: str
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    verification_detail: str = ""
    capability_id: str = ""
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "tool": self.tool,
            "status": self.status,
            "message": self.message,
            "result": dict(self.result),
            "capability_id": self.capability_id,
        }
        if self.verification_detail:
            payload["verification_detail"] = self.verification_detail
        return payload


@dataclass(slots=True)
class PendingState:
    active: bool = False
    kind: str = ""
    next_field: str = ""
    missing_fields: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=contract_timestamp)
    contract_version: str = CONTRACT_VERSION

    def to_dict(self, *, include_legacy_fields: bool = False) -> dict[str, Any]:
        payload = {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "active": self.active,
            "kind": self.kind,
            "next_field": self.next_field,
            "missing_fields": list(self.missing_fields),
            "details": dict(self.details),
            "updated_at": self.updated_at or contract_timestamp(),
        }
        if include_legacy_fields:
            payload.update(
                {
                    "data": dict(self.details),
                    "required": list(self.missing_fields),
                    "missing": list(self.missing_fields),
                    "at": payload["updated_at"],
                }
            )
            payload.update(dict(self.details))
        return payload


@dataclass(slots=True)
class ClassifierResult:
    intent: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_tools: bool = False
    needs_context: bool = False
    risk: str = "low"
    source: str = "classifier"
    raw_text: str = ""
    at: str = field(default_factory=contract_timestamp)
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "intent": self.intent,
            "params": dict(self.params),
            "confidence": float(self.confidence),
            "needs_tools": self.needs_tools,
            "needs_context": self.needs_context,
            "risk": self.risk,
            "source": self.source,
        }
        if self.raw_text:
            payload["raw_text"] = self.raw_text
        if self.at:
            payload["at"] = self.at
        return payload


@dataclass(slots=True)
class CapabilityDescriptor:
    capability_id: str
    tool_name: str
    action_type: str
    kind: TaskKind
    description: str
    aliases: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_tool_spec(cls, capability_id: str | None, spec: ToolSpec) -> "CapabilityDescriptor":
        return cls(
            capability_id=_text(capability_id) or _text(spec.capability_id),
            tool_name=spec.name,
            action_type=spec.action_type,
            kind=spec.kind,
            description=spec.description,
            aliases=tuple(spec.aliases),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version or CONTRACT_VERSION,
            "capability_id": self.capability_id,
            "tool_name": self.tool_name,
            "action_type": self.action_type,
            "kind": self.kind,
            "description": self.description,
            "aliases": list(self.aliases),
        }


@dataclass(slots=True)
class HudEventEnvelope:
    type: str
    data: JsonPayload = field(default_factory=dict)
    ts: str = field(default_factory=contract_timestamp)
    session_id: str = ""
    event_version: str = CONTRACT_VERSION

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None, *, default_type: str = "event") -> "HudEventEnvelope":
        data = payload if isinstance(payload, dict) else {}
        event_type = _text(data.get("type", "")) or default_type
        body = data.get("data", data.get("payload", {}))
        clean_data: JsonPayload = body if isinstance(body, (dict, list)) else {}
        return cls(
            type=event_type,
            data=clean_data,
            ts=_text(data.get("ts", "")) or contract_timestamp(),
            session_id=_text(data.get("session_id", "")),
            event_version=_text(data.get("event_version", "")) or CONTRACT_VERSION,
        )

    def to_dict(self, *, include_legacy_payload: bool = True) -> dict[str, Any]:
        payload = {
            "event_version": self.event_version or CONTRACT_VERSION,
            "type": _text(self.type) or "event",
            "ts": self.ts or contract_timestamp(),
            "data": self.data if isinstance(self.data, (dict, list)) else {},
        }
        if include_legacy_payload:
            payload["payload"] = payload["data"]
        if self.session_id:
            payload["session_id"] = self.session_id
        return payload
