"""
OpenTelemetry and Distributed Tracing Instrumentation Layer.
Provides correlation ID injection, W3C TraceContext propagation,
and span execution monitoring across HTTP, Redis Streams, LangGraph nodes, and MCP tools.
"""

import time
import uuid
from contextvars import ContextVar
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from pydantic import BaseModel, Field

# Context variables for request-scoped correlation tracking
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")
current_span_id: ContextVar[str] = ContextVar("current_span_id", default="")
current_correlation_id: ContextVar[str] = ContextVar("current_correlation_id", default="")


class SpanRecord(BaseModel):
    """Execution record for an instrumented diagnostic step."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    correlation_id: str
    name: str
    span_type: str  # "http", "stream", "langgraph_node", "mcp_tool"
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    status: str = "OK"  # "OK" or "ERROR"
    error_message: Optional[str] = None


class TelemetryRecorder:
    """Thread-safe recorder for live distributed telemetry spans."""

    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self._spans: List[SpanRecord] = []

    def record_span(self, span: SpanRecord):
        self._spans.append(span)
        if len(self._spans) > self.max_records:
            self._spans.pop(0)

    def get_spans_by_trace(self, trace_id: str) -> List[SpanRecord]:
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_spans_by_correlation(self, correlation_id: str) -> List[SpanRecord]:
        return [s for s in self._spans if s.correlation_id == correlation_id]

    def clear(self):
        self._spans.clear()


# Global telemetry singleton
telemetry_recorder = TelemetryRecorder()


def generate_trace_id() -> str:
    """Generates a 32-character hex trace ID conforming to W3C TraceContext."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generates a 16-character hex span ID conforming to W3C TraceContext."""
    return uuid.uuid4().hex[:16]


def generate_correlation_id() -> str:
    """Generates a human-readable correlation ID chain."""
    return f"corr-{uuid.uuid4().hex[:8]}"


def inject_correlation_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Injects W3C TraceContext and TracePilot correlation headers into an outgoing HTTP or stream payload."""
    trace_id = current_trace_id.get() or generate_trace_id()
    span_id = current_span_id.get() or generate_span_id()
    corr_id = current_correlation_id.get() or generate_correlation_id()

    headers["X-Correlation-ID"] = corr_id
    headers["traceparent"] = f"00-{trace_id}-{span_id}-01"
    return headers


def extract_correlation_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    """Extracts W3C TraceContext and TracePilot correlation IDs from incoming headers or message metadata."""
    corr_id = headers.get("X-Correlation-ID") or headers.get("x-correlation-id") or generate_correlation_id()
    traceparent = headers.get("traceparent") or headers.get("Traceparent")

    trace_id = generate_trace_id()
    parent_span_id = None

    if traceparent and isinstance(traceparent, str) and traceparent.startswith("00-"):
        parts = traceparent.split("-")
        if len(parts) >= 4:
            trace_id = parts[1]
            parent_span_id = parts[2]

    # Set context variables
    current_trace_id.set(trace_id)
    current_correlation_id.set(corr_id)
    new_span = generate_span_id()
    current_span_id.set(new_span)

    return {
        "trace_id": trace_id,
        "span_id": new_span,
        "parent_span_id": parent_span_id or "",
        "correlation_id": corr_id,
    }


def trace_step(step_name: str, span_type: str = "langgraph_node"):
    """Decorator to trace LangGraph nodes and MCP tools with telemetry spans."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            t_id = current_trace_id.get() or generate_trace_id()
            p_span = current_span_id.get() or None
            s_id = generate_span_id()
            c_id = current_correlation_id.get() or generate_correlation_id()

            # Set current span
            token_span = current_span_id.set(s_id)
            start_t = time.time()
            status = "OK"
            err_msg = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "ERROR"
                err_msg = str(e)
                raise
            finally:
                end_t = time.time()
                dur_ms = round((end_t - start_t) * 1000, 2)
                span = SpanRecord(
                    span_id=s_id,
                    trace_id=t_id,
                    parent_span_id=p_span,
                    correlation_id=c_id,
                    name=step_name,
                    span_type=span_type,
                    start_time=start_t,
                    end_time=end_t,
                    duration_ms=dur_ms,
                    attributes={"function": func.__name__},
                    status=status,
                    error_message=err_msg,
                )
                telemetry_recorder.record_span(span)
                current_span_id.reset(token_span)

        return wrapper
    return decorator
