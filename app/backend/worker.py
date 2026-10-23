"""
Background Worker for Stream-Driven Autonomous Incident Investigations.
Implements consumer groups, distributed atomic lease locking, LangGraph coordination,
and Dead Letter Queue (DLQ) error recovery.
"""

import time
import uuid
import logging
import threading
from typing import Optional

from app.backend.streaming import BaseEventStream, get_event_stream
from app.backend.idempotency import idempotency_manager
from app.backend.repository import repository
from app.schemas.incidents import IncidentStatus
from app.schemas.investigation import InvestigationStatus
from app.workflow.engine import InvestigationEngine

logger = logging.getLogger(__name__)


class BackgroundInvestigationWorker:
    """Asynchronous worker consuming alert events from streaming queues

    and driving autonomous LangGraph investigation workflows with lease isolation.
    """

    def __init__(
        self,
        stream: Optional[BaseEventStream] = None,
        stream_name: str = "stream:alerts",
        group_name: str = "investigation-workers",
        consumer_name: Optional[str] = None,
        max_retries: int = 3,
        lease_seconds: float = 120.0,
        poll_interval: float = 0.5,
    ):
        self.stream = stream or get_event_stream()
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name or f"worker-{uuid.uuid4().hex[:6]}"
        self.max_retries = max_retries
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._engine: Optional[InvestigationEngine] = None

    @property
    def engine(self) -> InvestigationEngine:
        if self._engine is None:
            self._engine = InvestigationEngine()
        return self._engine

    def process_batch(self, count: int = 10) -> int:
        """Consumes and executes a single batch of alert messages synchronously.
        Returns the number of messages successfully processed.
        """
        messages = self.stream.consume(
            stream=self.stream_name,
            group=self.group_name,
            consumer=self.consumer_name,
            count=count,
        )

        if not messages:
            return 0

        processed = 0
        for msg in messages:
            incident_id = msg.data.get("incident_id")
            if not incident_id:
                # Malformed event without incident_id, ack and discard
                self.stream.ack(self.stream_name, self.group_name, msg.message_id)
                continue

            incident = repository.get_incident(incident_id)
            if not incident:
                logger.warning("Incident %s not found in repository. Acking message.", incident_id)
                self.stream.ack(self.stream_name, self.group_name, msg.message_id)
                continue

            # Attempt to acquire exclusive lease to prevent duplicate runs across nodes
            if not idempotency_manager.acquire_lease(incident_id, lease_seconds=self.lease_seconds):
                logger.info(
                    "Incident %s is actively leased by another worker. Skipping duplicate run.",
                    incident_id,
                )
                continue

            # Find or create investigation tracking record
            inv_id = msg.data.get("investigation_id")
            if inv_id:
                inv = repository.get_investigation(inv_id)
            else:
                inv = repository.create_investigation(incident_id)
                inv_id = inv.id

            try:
                # Update status to RUNNING
                repository.update_incident_status(incident_id, IncidentStatus.INVESTIGATING)
                repository.update_investigation(inv_id, InvestigationStatus.RUNNING)

                # Execute autonomous LangGraph investigation workflow
                result = self.engine.run_investigation(
                    incident_id=incident_id,
                    title=incident.title,
                    description=incident.description,
                    affected_service=incident.affected_service,
                    severity=incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
                    environment=incident.environment,
                )

                final_report = result.get("final_report")
                if final_report:
                    repository.save_report(final_report)
                    repository.update_investigation(
                        inv_id, InvestigationStatus.COMPLETED, report=final_report
                    )
                    repository.update_incident_status(incident_id, IncidentStatus.REPORT_READY)
                else:
                    repository.update_investigation(
                        inv_id,
                        InvestigationStatus.FAILED,
                        error_message="Workflow finished without generating final report",
                    )
                    repository.update_incident_status(incident_id, IncidentStatus.FAILED)

                # Acknowledge successful processing
                self.stream.ack(self.stream_name, self.group_name, msg.message_id)
                processed += 1

            except Exception as e:
                logger.exception("Error processing investigation for incident %s: %s", incident_id, e)
                if msg.attempts >= self.max_retries:
                    self.stream.dead_letter(
                        self.stream_name, self.group_name, msg.message_id, error=str(e)
                    )
                    repository.update_investigation(
                        inv_id, InvestigationStatus.FAILED, error_message=str(e)
                    )
                    repository.update_incident_status(incident_id, IncidentStatus.FAILED)
                else:
                    # Increment attempt count
                    msg.attempts += 1
            finally:
                # Release distributed lease
                idempotency_manager.release_lease(incident_id)

        return processed

    def _worker_loop(self):
        """Continuous background polling loop."""
        while self._running:
            try:
                self.process_batch(count=10)
            except Exception as e:
                logger.error("Unexpected worker loop exception: %s", e)
            time.sleep(self.poll_interval)

    def start(self):
        """Starts the background worker thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name=self.consumer_name)
        self._thread.start()
        logger.info("BackgroundInvestigationWorker %s started.", self.consumer_name)

    def stop(self, timeout: float = 2.0):
        """Stops the background worker thread."""
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("BackgroundInvestigationWorker %s stopped.", self.consumer_name)
