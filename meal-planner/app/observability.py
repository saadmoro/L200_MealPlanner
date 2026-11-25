"""OpenTelemetry tracing setup for local JSONL inspection, OTLP (Phoenix/Jaeger), and Cloud Trace."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_LOG = PROJECT_ROOT / "logs" / "traces.jsonl"

_CONFIGURED = False


class JsonlFileSpanExporter(SpanExporter):
    """Exports every OpenTelemetry span as a JSON line for local auditing & deterministic tests."""

    def __init__(self, file_path: Path | str = DEFAULT_TRACE_LOG) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            with self.file_path.open("a", encoding="utf-8") as fh:
                for span in spans:
                    ctx = span.get_span_context()
                    record: dict[str, Any] = {
                        "name": span.name,
                        "trace_id": format(ctx.trace_id, "032x"),
                        "span_id": format(ctx.span_id, "016x"),
                        "parent_span_id": (
                            format(span.parent.span_id, "016x") if span.parent else None
                        ),
                        "start_time_ns": span.start_time,
                        "end_time_ns": span.end_time,
                        "status": span.status.status_code.name,
                        "attributes": dict(span.attributes) if span.attributes else {},
                        "events": [
                            {
                                "name": ev.name,
                                "timestamp": ev.timestamp,
                                "attributes": dict(ev.attributes) if ev.attributes else {},
                            }
                            for ev in span.events
                        ],
                    }
                    fh.write(json.dumps(record, default=str) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        return None


def configure_local_otel(
    trace_log_path: Path | str | None = None,
    force: bool = False,
) -> TracerProvider:
    """Configure OpenTelemetry tracing with JSONL file export and optional OTLP HTTP export.

    Set ``OTEL_EXPORTER_OTLP_ENDPOINT`` (e.g., ``http://localhost:4318/v1/traces``) to stream
    spans to a local Arize Phoenix or Jaeger collector in addition to ``logs/traces.jsonl``.
    """
    global _CONFIGURED
    existing = trace.get_tracer_provider()
    if _CONFIGURED and not force and isinstance(existing, TracerProvider):
        return existing

    if isinstance(existing, TracerProvider):
        provider = existing
    else:
        resource = Resource.create(
            {
                "service.name": "meal-planner-agent",
                "service.version": "0.1.0",
                "deployment.environment": os.environ.get("ENVIRONMENT", "local-prototype"),
            }
        )
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

    log_path = Path(
        trace_log_path
        or os.environ.get("MEAL_PLANNER_TRACE_LOG", str(DEFAULT_TRACE_LOG))
    )
    provider.add_span_processor(SimpleSpanProcessor(JsonlFileSpanExporter(log_path)))

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )

    _CONFIGURED = True
    return provider


def get_tracer(name: str = "meal_planner") -> trace.Tracer:
    """Return the OpenTelemetry tracer for custom workflow/tool spans."""
    return trace.get_tracer(name)
