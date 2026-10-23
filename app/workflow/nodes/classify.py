"""
Classify Node: Initial triage of the incoming incident alert.
Normalizes target service, severity, and initializes investigation state.
"""

from typing import Dict, Any
from app.workflow.state import InvestigationState


def classify_node(state: InvestigationState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "INC-LIVE")
    affected_svc = state.get("affected_service", "checkout-service")
    severity = state.get("severity", "P1")

    trace_msg = (
        f"[CLASSIFY] Triaged incident {incident_id}: Affected service is '{affected_svc}' "
        f"with severity {severity}. Initiating multi-agent diagnostic run."
    )

    return {
        "current_focus_service": affected_svc,
        "visited_services": [affected_svc],
        "iteration_count": 1,
        "max_iterations": state.get("max_iterations", 3),
        "status": "TRIAGED",
        "execution_trace": [trace_msg]
    }
