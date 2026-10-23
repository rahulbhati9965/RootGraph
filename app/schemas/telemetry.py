from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ServiceNode(BaseModel):
    """Represents a microservice node in the architecture graph."""
    id: str
    name: str
    region: str
    tier: str
    team: str
    protocol: str = "http"
    health_status: str = "healthy"
    is_external: bool = False
    dependencies: List[str] = Field(default_factory=list)


class DependencyEdge(BaseModel):
    """Represents a directed communication call/dependency between two services."""
    source: str
    target: str
    type: str = "SYNC_CALL"
    timeout_ms: int = 1000
    circuit_breaker_enabled: bool = False


class TopologyData(BaseModel):
    """Full architecture topology specification."""
    topology_version: str = "1.0"
    environment: str = "production"
    services: List[ServiceNode]
    dependency_edges: List[DependencyEdge]


class Span(BaseModel):
    """Represents an OpenTelemetry-compatible span in a distributed trace."""
    span_id: str
    parent_span_id: Optional[str] = None
    service_name: str
    operation_name: str
    region: str
    start_offset_ms: int
    duration_ms: int
    status_code: int = 200
    status: str = "OK"  # OK, WARN, ERROR
    correlation_id: Optional[str] = None
    is_slow: bool = False
    tags: Dict[str, Any] = Field(default_factory=dict)


class TraceWaterfall(BaseModel):
    """Represents a full distributed trace with waterfall spans and correlation path."""
    trace_id: str
    start_time: str
    duration_ms: int
    status: str  # OK, WARN, ERROR
    services_count: int
    spans_count: int
    errors_count: int
    correlation_chain: List[str] = Field(default_factory=list)
    spans: List[Span]


class LogEntry(BaseModel):
    """Structured log record correlated with trace and span IDs."""
    timestamp: str
    service: str
    level: str  # INFO, WARN, ERROR, DEBUG
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    message: str
    region: str
    error_details: Optional[Dict[str, Any]] = None


class ServiceMetricItem(BaseModel):
    service: str
    error_rate_pct: float
    p95_latency_ms: int


class RegionalMetricItem(BaseModel):
    region: str
    error_rate_pct: float
    primary_culprit: str


class ErrorTypeItem(BaseModel):
    type: str
    count: int
    percentage: float


class MetricTimelinePoint(BaseModel):
    time: str
    error_rate_pct: float
    p95_latency_ms: int
    throughput_rps: int


class MetricSummary(BaseModel):
    """Golden signals metrics summary."""
    timestamp: str
    time_window_minutes: int
    summary: Dict[str, float]
    top_services_by_error_rate: List[ServiceMetricItem]
    error_rate_by_region: List[RegionalMetricItem]
    errors_by_type: List[ErrorTypeItem]
    timeline_points: List[MetricTimelinePoint]
