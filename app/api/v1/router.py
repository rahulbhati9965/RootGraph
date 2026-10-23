"""
FastAPI REST API Router (v1) for TracePilot.
Provides endpoints for alert ingestion with idempotency deduplication,
incident management, LangGraph investigation dispatching, and report retrieval.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.schemas.incidents import IncidentCreate, IncidentRead, IncidentStatus
from app.schemas.investigation import (
    InvestigationRecord,
    InvestigationReport,
    InvestigationStatus,
)
from app.backend.idempotency import idempotency_manager
from app.backend.streaming import get_event_stream
from app.backend.repository import repository
from app.workflow.engine import InvestigationEngine

router = APIRouter()


@router.get("/health")
def health_check():
    """Liveness and readiness probe for TracePilot backend."""
    return {
        "status": "healthy",
        "service": "TracePilot Distributed Backend",
        "version": "1.0.0",
        "stream_backend": settings.stream_backend,
        "storage_backend": settings.storage_backend,
    }


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
def ingest_alert(alert: IncidentCreate, response: Response):
    """Webhook ingestion endpoint for alerts with SHA-256 idempotency deduplication.
    Identical alerts firing within a 5-minute sliding window return cached responses
    with the X-Idempotent-Replay: true header, preventing alert storm cascades.
    """
    fingerprint = idempotency_manager.compute_fingerprint(
        service=alert.affected_service,
        title=alert.title,
        environment=alert.environment,
        time_bucket_minutes=5,
    )

    is_duplicate, existing_record = idempotency_manager.check_and_register(
        fingerprint=fingerprint,
        record=None,  # placeholder before persistence
    )

    if is_duplicate and existing_record is not None:
        response.headers["X-Idempotent-Replay"] = "true"
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            headers={"X-Idempotent-Replay": "true"},
            content={
                "status": "deduplicated",
                "idempotent_replay": True,
                "incident": existing_record,
                "fingerprint": fingerprint,
            },
        )

    # Novel incident: persist to repository
    incident = repository.create_incident(alert)
    incident_dict = incident.model_dump(mode="json")

    # Update idempotency store with the actual persisted record
    idempotency_manager._fingerprints[fingerprint] = (
        incident_dict,
        idempotency_manager._fingerprints[fingerprint][1],
    )

    # Publish alert event to stream
    stream = get_event_stream()
    stream.publish(
        stream="stream:alerts",
        data={
            "event": "alert_received",
            "incident_id": incident.id,
            "service": incident.affected_service,
            "severity": incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
        },
    )

    response.headers["X-Idempotent-Replay"] = "false"
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        headers={"X-Idempotent-Replay": "false"},
        content={
            "status": "created",
            "idempotent_replay": False,
            "incident": incident_dict,
            "fingerprint": fingerprint,
        },
    )


@router.post("/incidents", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
def create_incident(incident_in: IncidentCreate):
    """Directly creates a new incident record."""
    return repository.create_incident(incident_in)


@router.get("/incidents", response_model=List[IncidentRead])
def list_incidents(
    incident_status: Optional[IncidentStatus] = Query(None, alias="status"),
    service: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Lists incidents with optional filtering by status and service."""
    return repository.list_incidents(status=incident_status, service=service, limit=limit)


@router.get("/incidents/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: str):
    """Retrieves an incident by its unique ID."""
    incident = repository.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


@router.post("/incidents/{incident_id}/investigations")
def trigger_investigation(
    incident_id: str,
    sync: bool = Query(False, description="Whether to execute synchronously or enqueue via stream"),
):
    """Triggers an autonomous LangGraph investigation for an incident.
    Supports synchronous execution (sync=true) or async event-stream dispatching (sync=false).
    """
    incident = repository.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    if sync:
        # Check exclusive lease
        if not idempotency_manager.acquire_lease(incident_id, lease_seconds=120.0):
            raise HTTPException(
                status_code=409,
                detail=f"Incident {incident_id} is currently being investigated by another worker",
            )

        inv = repository.create_investigation(incident_id)
        repository.update_incident_status(incident_id, IncidentStatus.INVESTIGATING)
        repository.update_investigation(inv.id, InvestigationStatus.RUNNING)

        try:
            engine = InvestigationEngine()
            result = engine.run_investigation(
                incident_id=incident.id,
                title=incident.title,
                description=incident.description,
                affected_service=incident.affected_service,
                severity=incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
                environment=incident.environment,
            )

            report = result.get("final_report")
            if report:
                repository.save_report(report)
                repository.update_investigation(inv.id, InvestigationStatus.COMPLETED, report=report)
                repository.update_incident_status(incident_id, IncidentStatus.REPORT_READY)
                return {
                    "investigation_id": inv.id,
                    "status": "COMPLETED",
                    "report": report.model_dump(mode="json"),
                }
            else:
                repository.update_investigation(
                    inv.id, InvestigationStatus.FAILED, error_message="Failed to generate report"
                )
                repository.update_incident_status(incident_id, IncidentStatus.FAILED)
                return {
                    "investigation_id": inv.id,
                    "status": "FAILED",
                    "error": "Investigation finished without report",
                }
        except Exception as e:
            repository.update_investigation(
                inv.id, InvestigationStatus.FAILED, error_message=str(e)
            )
            repository.update_incident_status(incident_id, IncidentStatus.FAILED)
            raise HTTPException(status_code=500, detail=f"Investigation workflow error: {e}")
        finally:
            idempotency_manager.release_lease(incident_id)

    else:
        # Enqueue via stream for asynchronous background worker
        inv = repository.create_investigation(incident_id)
        stream = get_event_stream()
        msg_id = stream.publish(
            stream="stream:alerts",
            data={
                "event": "start_investigation",
                "incident_id": incident_id,
                "investigation_id": inv.id,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "investigation_id": inv.id,
                "status": "PENDING",
                "stream_message_id": msg_id,
                "message": "Investigation enqueued for processing by background workers",
            },
        )


@router.get("/investigations/{investigation_id}", response_model=InvestigationRecord)
def get_investigation(investigation_id: str):
    """Retrieves the status and execution record of an investigation."""
    record = repository.get_investigation(investigation_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Investigation {investigation_id} not found")
    return record


@router.get("/incidents/{incident_id}/report", response_model=InvestigationReport)
def get_incident_report(incident_id: str):
    """Retrieves the completed SRE InvestigationReport for an incident."""
    incident = repository.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    report = repository.get_report(incident_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation report not ready for incident {incident_id}. Status: {incident.status.value}",
        )
    return report
