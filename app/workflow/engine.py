"""
Investigation Engine: High-level coordinator executing LangGraph incident workflows.
Invokes the compiled StateGraph and yields structured InvestigationReports.
"""

import uuid
from typing import Dict, Any, Optional
from app.workflow.graph import build_investigation_graph
from app.workflow.state import InvestigationState
from app.schemas.incidents import IncidentCreate
from app.schemas.investigation import InvestigationReport


class InvestigationEngine:
    """High-level runner for autonomous LangGraph incident investigations."""

    def __init__(self):
        self.graph = build_investigation_graph()

    def run_investigation(
        self,
        incident_id: str,
        title: str,
        description: str,
        affected_service: str,
        severity: str = "P1",
        environment: str = "production",
        max_iterations: int = 3
    ) -> Dict[str, Any]:
        """Synchronously executes the full LangGraph investigation workflow."""
        initial_state: InvestigationState = {
            "incident_id": incident_id,
            "title": title,
            "description": description,
            "affected_service": affected_service,
            "current_focus_service": affected_service,
            "severity": severity,
            "environment": environment,
            "iteration_count": 1,
            "max_iterations": max_iterations,
            "visited_services": [affected_service],
            "evidence_cards": [],
            "execution_trace": [f"[START] Starting investigation session for {incident_id}."],
            "is_conclusive": False,
            "confidence_score": 0.0,
            "status": "INITIALIZED"
        }

        # Invoke the LangGraph workflow
        final_state = self.graph.invoke(initial_state)
        return final_state

    def investigate(self, incident: IncidentCreate, incident_id: Optional[str] = None) -> InvestigationReport:
        """Executes investigation on an IncidentCreate model and returns the final InvestigationReport."""
        inc_id = incident_id or f"INC-{uuid.uuid4().hex[:8]}"
        state = self.run_investigation(
            incident_id=inc_id,
            title=incident.title,
            description=incident.description,
            affected_service=incident.affected_service,
            severity=incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
            environment=incident.environment
        )
        return state.get("final_report")
