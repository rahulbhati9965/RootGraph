"""
Strictly typed Pydantic v2 schemas for all 8 MCP Diagnostic Tools.
Enforces schema validation, boundaries, and read-only parameter sanitization.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional
import re


# Common injection sanitizer pattern
DANGEROUS_PATTERNS = re.compile(r"(--|;|/\*|\*/|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bSHUTDOWN\b|`|\$)", re.IGNORECASE)


def sanitize_read_only_text(value: Optional[str]) -> Optional[str]:
    if value is not None and DANGEROUS_PATTERNS.search(value):
        raise ValueError(f"Dangerous character or mutating keyword detected in input: '{value}'")
    return value


# --- Tool 1: search_logs ---

class SearchLogsInput(BaseModel):
    service_name: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_\-]+$", description="Microservice identifier")
    trace_id: Optional[str] = Field(None, description="OpenTelemetry trace correlation ID")
    level: Optional[str] = Field(None, pattern=r"^(INFO|WARN|WARNING|ERROR|DEBUG)$", description="Log level severity")
    time_window: Optional[str] = Field(None, description="ISO-8601 or relative time window, e.g. '15m'")
    query: Optional[str] = Field(None, max_length=200, description="Free-text substring to search in log messages")
    limit: int = Field(50, ge=1, le=100, description="Maximum number of logs to return (1-100)")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        return sanitize_read_only_text(v)


class SearchLogsOutput(BaseModel):
    total_found: int
    service_name: Optional[str]
    level_filter: Optional[str]
    logs: List[Dict[str, Any]]


# --- Tool 2: query_metrics ---

class QueryMetricsInput(BaseModel):
    service_name: str = Field(..., pattern=r"^[a-zA-Z0-9_\-]+$", description="Target microservice identifier")
    metric_name: str = Field(..., max_length=100, description="Metric name e.g. error_rate, latency, cpu, saturation")
    start_time: Optional[str] = Field(None, description="Query start timestamp")
    end_time: Optional[str] = Field(None, description="Query end timestamp")
    step: Optional[str] = Field(None, description="Metric resolution step e.g. '15s', '1m'")


class QueryMetricsOutput(BaseModel):
    service_name: str
    metric_name: str
    status: str = "success"
    summary: Dict[str, Any]
    regional_breakdown: Optional[Dict[str, float]] = None


# --- Tool 3: search_traces ---

class SearchTracesInput(BaseModel):
    service_name: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_\-]+$", description="Filter by service name in spans")
    start_time: Optional[str] = Field(None, description="Search start time")
    end_time: Optional[str] = Field(None, description="Search end time")
    min_duration: Optional[int] = Field(None, ge=0, description="Minimum trace execution duration in milliseconds")
    status_filter: Optional[str] = Field(None, pattern=r"^(OK|WARN|ERROR)$", description="Trace overall status")
    limit: int = Field(10, ge=1, le=50, description="Maximum traces to retrieve")


class SearchTracesOutput(BaseModel):
    total_found: int
    traces: List[Dict[str, Any]]


# --- Tool 4: get_service_dependencies ---

class GetServiceDependenciesInput(BaseModel):
    service_name: str = Field(..., pattern=r"^[a-zA-Z0-9_\-]+$", description="Source microservice name")
    max_depth: int = Field(3, ge=1, le=5, description="Maximum graph hops to traverse (1-5)")
    direction: str = Field("downstream", pattern=r"^(downstream|upstream)$", description="Graph traversal direction ('downstream' or 'upstream')")


class GetServiceDependenciesOutput(BaseModel):
    service_name: str
    direction: str
    max_depth: int
    dependencies: List[Dict[str, Any]]
    blast_radius: List[str] = Field(default_factory=list)


# --- Tool 5: search_runbooks ---

class SearchRunbooksInput(BaseModel):
    query: str = Field(..., min_length=2, max_length=300, description="Incident symptom or alert query")
    service_name: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_\-]+$", description="Optional target service to filter or boost")
    limit: int = Field(3, ge=1, le=10, description="Maximum runbook chunks to return")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        return sanitize_read_only_text(v)


class SearchRunbooksOutput(BaseModel):
    query: str
    total_found: int
    top_runbooks: List[Dict[str, Any]]


# --- Tool 6: find_similar_incidents ---

class FindSimilarIncidentsInput(BaseModel):
    incident_description: str = Field(..., min_length=3, max_length=500, description="Symptoms and timeline of the current incident")
    service_name: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_\-]+$", description="Impacted service")
    limit: int = Field(3, ge=1, le=10, description="Number of past incidents to retrieve")

    @field_validator("incident_description")
    @classmethod
    def validate_desc(cls, v):
        return sanitize_read_only_text(v)


class FindSimilarIncidentsOutput(BaseModel):
    total_found: int
    similar_incidents: List[Dict[str, Any]]


# --- Tool 7: get_deployment_history ---

class GetDeploymentHistoryInput(BaseModel):
    service_name: str = Field(..., pattern=r"^[a-zA-Z0-9_\-]+$", description="Microservice to inspect for recent deployments")
    start_time: Optional[str] = Field(None, description="Start timestamp")
    end_time: Optional[str] = Field(None, description="End timestamp")


class GetDeploymentHistoryOutput(BaseModel):
    service_name: str
    total_deployments: int
    latest_deployment: Optional[Dict[str, Any]] = None
    deployments: List[Dict[str, Any]]


# --- Tool 8: save_investigation_note ---

class SaveInvestigationNoteInput(BaseModel):
    incident_id: str = Field(..., min_length=1, max_length=100, description="Unique incident identifier")
    note: str = Field(..., min_length=1, max_length=2000, description="Agent observation, hypothesis, or diagnostic reasoning")
    evidence_references: List[str] = Field(default_factory=list, description="List of IDs (spans, logs, metrics) supporting this note")

    @field_validator("note")
    @classmethod
    def validate_note(cls, v):
        return sanitize_read_only_text(v)


class SaveInvestigationNoteOutput(BaseModel):
    status: str = "saved"
    incident_id: str
    note_id: str
    saved_at: str
    evidence_count: int
