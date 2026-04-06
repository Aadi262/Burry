#!/usr/bin/env python3
"""OpenTelemetry tracing — full pipeline observability.
Every voice command is traced from STT through intent to tool call to TTS.
Stolen from AgentScope observability pattern.
"""
from __future__ import annotations

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource

    _provider = TracerProvider(resource=Resource.create({"service.name": "burry-os"}))
    _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)
    tracer = trace.get_tracer("burry.voice_pipeline")
    _OTEL_AVAILABLE = True
except Exception:
    _OTEL_AVAILABLE = False
    tracer = None


def trace_command(func):
    """Decorator that wraps a function in an OTel span (no-op if OTel unavailable)."""
    if not _OTEL_AVAILABLE:
        return func

    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__) as span:
            try:
                result = func(*args, **kwargs)
                span.set_status(trace.StatusCode.OK)
                return result
            except Exception as exc:
                span.set_status(trace.StatusCode.ERROR, str(exc))
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
    if span:
        span.add_event(name, attributes or {})
