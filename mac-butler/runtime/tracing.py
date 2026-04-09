#!/usr/bin/env python3
"""OpenTelemetry tracing — full pipeline observability.
Every voice command is traced from STT through intent to tool call to TTS.
Stolen from AgentScope observability pattern.
"""
from __future__ import annotations

import atexit
import os

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SpanExporter,
        SpanExportResult,
    )
    from opentelemetry.sdk.resources import Resource

    try:
        from .log_store import append_trace_span
    except Exception:  # pragma: no cover - package/script fallback
        from runtime.log_store import append_trace_span

    def _json_safe(value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)

    class _JsonlSpanExporter(SpanExporter):
        def export(self, spans) -> SpanExportResult:
            for span in spans:
                try:
                    context = span.get_span_context()
                    parent = getattr(span, "parent", None)
                    append_trace_span(
                        {
                            "name": str(getattr(span, "name", "") or ""),
                            "trace_id": format(getattr(context, "trace_id", 0), "032x"),
                            "span_id": format(getattr(context, "span_id", 0), "016x"),
                            "parent_span_id": format(getattr(parent, "span_id", 0), "016x") if parent else "",
                            "start_time_unix_nano": int(getattr(span, "start_time", 0) or 0),
                            "end_time_unix_nano": int(getattr(span, "end_time", 0) or 0),
                            "status": getattr(getattr(span, "status", None), "status_code", None).name
                            if getattr(getattr(span, "status", None), "status_code", None) is not None
                            else "",
                            "attributes": _json_safe(dict(getattr(span, "attributes", {}) or {})),
                            "events": [
                                {
                                    "name": str(getattr(event, "name", "") or ""),
                                    "timestamp": int(getattr(event, "timestamp", 0) or 0),
                                    "attributes": _json_safe(dict(getattr(event, "attributes", {}) or {})),
                                }
                                for event in list(getattr(span, "events", []) or [])
                            ],
                        }
                    )
                except Exception:
                    continue
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            return None

    _provider = TracerProvider(resource=Resource.create({"service.name": "burry-os"}))
    _provider.add_span_processor(BatchSpanProcessor(_JsonlSpanExporter()))
    if os.environ.get("BURRY_TRACE_TO_CONSOLE", "").strip().lower() in {"1", "true", "yes", "on"}:
        _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)
    tracer = trace.get_tracer("burry.voice_pipeline")
    _OTEL_AVAILABLE = True
except Exception:
    _OTEL_AVAILABLE = False
    tracer = None
    _provider = None

_TRACING_SHUTDOWN = False


def shutdown_tracing() -> None:
    global _TRACING_SHUTDOWN
    if _TRACING_SHUTDOWN or not _OTEL_AVAILABLE or _provider is None:
        return
    try:
        _provider.shutdown()
    except Exception:
        pass
    _TRACING_SHUTDOWN = True


atexit.register(shutdown_tracing)


def trace_command(func):
    """Decorator that wraps a function in an OTel span (no-op if OTel unavailable)."""
    if not _OTEL_AVAILABLE:
        return func

    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__) as span:
            try:
                result = func(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def add_event(name: str, attributes: dict | None = None) -> None:
    """Add a named event to the current span."""
    if not _OTEL_AVAILABLE:
        return
    span = trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes or {})
