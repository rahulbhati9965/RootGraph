from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class Severity(str, Enum):
    P0 = "P0"  # Critical outage (e.g. all checkouts failing)
    P1 = "P1"  # Major degradation
    P2 = "P2"  # Moderate impact
    P3 = "P3"  # Minor / cosmetic


class IncidentStatus(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    REPORT_READY = "REPORT_READY"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class IncidentCreate(BaseModel):
    title: str
    description: str
    severity: Severity = Severity.P1
    affected_service: str
    environment: str = "production"
    correlation_id: Optional[str] = None


class IncidentRead(BaseModel):
    id: str
    title: str
    description: str
    severity: Severity
    status: IncidentStatus
    affected_service: str
    environment: str
    correlation_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None


class IncidentEvent(BaseModel):
    event_id: str
    incident_id: Optional[str] = None
    source: str
    event_type: str
    severity: Severity
    timestamp: str
    correlation_id: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
