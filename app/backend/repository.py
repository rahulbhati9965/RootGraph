"""
In-Memory Thread-Safe Repository for Incidents, Investigations, and Reports.
Provides fast, zero-daemon persistence with query filtering and atomic updates.
"""

import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.schemas.incidents import IncidentCreate, IncidentRead, IncidentStatus, Severity
from app.schemas.investigation import (
    InvestigationRecord,
    InvestigationStatus,
    InvestigationReport,
)


class IncidentRepository:
    """Thread-safe storage repository for incidents, investigations, and SRE reports."""

    def __init__(self):
        self._incidents: Dict[str, IncidentRead] = {}
        self._investigations: Dict[str, InvestigationRecord] = {}
        self._reports: Dict[str, InvestigationReport] = {}  # incident_id -> report
        self._lock = threading.Lock()

    def create_incident(
        self,
        incident_in: IncidentCreate,
        incident_id: Optional[str] = None,
    ) -> IncidentRead:
        """Persists a new incident record."""
        now = datetime.now(timezone.utc)
        inc_id = incident_id or f"INC-{uuid.uuid4().hex[:8]}"

        record = IncidentRead(
            id=inc_id,
            title=incident_in.title,
            description=incident_in.description,
            severity=incident_in.severity,
            status=IncidentStatus.NEW,
            affected_service=incident_in.affected_service,
            environment=incident_in.environment,
            correlation_id=incident_in.correlation_id,
            created_at=now,
            updated_at=now,
            resolved_at=None,
        )

        with self._lock:
            self._incidents[inc_id] = record
            return record

    def get_incident(self, incident_id: str) -> Optional[IncidentRead]:
        """Fetches an incident by its unique ID."""
        with self._lock:
            return self._incidents.get(incident_id)

    def list_incidents(
        self,
        status: Optional[IncidentStatus] = None,
        service: Optional[str] = None,
        limit: int = 50,
    ) -> List[IncidentRead]:
        """Lists incidents with optional status and service filtering."""
        with self._lock:
            results = list(self._incidents.values())

        if status:
            results = [inc for inc in results if inc.status == status]
        if service:
            svc_lower = service.lower().strip()
            results = [inc for inc in results if inc.affected_service.lower() == svc_lower]

        # Sort descending by creation time
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    def update_incident_status(
        self,
        incident_id: str,
        status: IncidentStatus,
    ) -> Optional[IncidentRead]:
        """Updates the lifecycle status of an incident."""
        now = datetime.now(timezone.utc)
        with self._lock:
            inc = self._incidents.get(incident_id)
            if not inc:
                return None

            resolved_time = now if status == IncidentStatus.RESOLVED else inc.resolved_at
            updated = inc.model_copy(
                update={"status": status, "updated_at": now, "resolved_at": resolved_time}
            )
            self._incidents[incident_id] = updated
            return updated

    def create_investigation(
        self,
        incident_id: str,
        investigation_id: Optional[str] = None,
    ) -> InvestigationRecord:
        """Creates a new tracking record for an agent investigation run."""
        now = datetime.now(timezone.utc)
        inv_id = investigation_id or f"INV-{uuid.uuid4().hex[:8]}"

        record = InvestigationRecord(
            id=inv_id,
            incident_id=incident_id,
            status=InvestigationStatus.PENDING,
            graph_thread_id=f"thread-{uuid.uuid4().hex[:6]}",
            attempt_number=1,
            started_at=now,
            completed_at=None,
            error_message=None,
            report=None,
        )

        with self._lock:
            self._investigations[inv_id] = record
            return record

    def get_investigation(self, investigation_id: str) -> Optional[InvestigationRecord]:
        """Fetches an investigation execution record."""
        with self._lock:
            return self._investigations.get(investigation_id)

    def get_investigations_for_incident(self, incident_id: str) -> List[InvestigationRecord]:
        """Retrieves all investigations executed for a specific incident."""
        with self._lock:
            invs = [inv for inv in self._investigations.values() if inv.incident_id == incident_id]
        invs.sort(key=lambda x: x.started_at, reverse=True)
        return invs

    def update_investigation(
        self,
        investigation_id: str,
        status: InvestigationStatus,
        report: Optional[InvestigationReport] = None,
        error_message: Optional[str] = None,
    ) -> Optional[InvestigationRecord]:
        """Updates the status and optional report of an investigation."""
        now = datetime.now(timezone.utc)
        with self._lock:
            inv = self._investigations.get(investigation_id)
            if not inv:
                return None

            completed_time = now if status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED) else None
            updated = inv.model_copy(
                update={
                    "status": status,
                    "completed_at": completed_time or inv.completed_at,
                    "report": report or inv.report,
                    "error_message": error_message or inv.error_message,
                }
            )
            self._investigations[investigation_id] = updated
            return updated

    def save_report(self, report: InvestigationReport) -> InvestigationReport:
        """Persists the final SRE InvestigationReport keyed by incident_id."""
        with self._lock:
            self._reports[report.incident_id] = report
            return report

    def get_report(self, incident_id: str) -> Optional[InvestigationReport]:
        """Retrieves the latest investigation report for an incident."""
        with self._lock:
            return self._reports.get(incident_id)

    def clear(self):
        """Resets all stored data (for test teardowns)."""
        with self._lock:
            self._incidents.clear()
            self._investigations.clear()
            self._reports.clear()


# Global singleton repository
repository = IncidentRepository()
