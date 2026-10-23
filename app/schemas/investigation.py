from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime


class InvestigationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvidenceCard(BaseModel):
    """An empirical piece of diagnostic evidence."""
    source: str  # "trace_span", "log_entry", "metric_anomaly", "service_graph", "runbook"
    reference: str  # e.g. span ID, log timestamp, graph path, runbook code
    finding: str  # specific empirical observation
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    """A ranked root-cause hypothesis backed by evidence."""
    rank: int
    title: str
    culprit_service: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: List[EvidenceCard] = Field(default_factory=list)
    contradicting_evidence: List[EvidenceCard] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    """Final structured incident investigation report."""
    incident_id: str
    status: str = "investigated"
    summary: str
    root_cause_service: str
    affected_service: str
    blast_radius: List[str] = Field(default_factory=list)
    confidence_score: float
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    recommended_checks: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    correlation_chain: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class InvestigationRecord(BaseModel):
    """Investigation execution record."""
    id: str
    incident_id: str
    status: InvestigationStatus
    graph_thread_id: str
    attempt_number: int = 1
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    report: Optional[InvestigationReport] = None
