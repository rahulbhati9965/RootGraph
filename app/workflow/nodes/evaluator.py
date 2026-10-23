"""
Evaluator-Optimizer Conditional Routing Edge.
Determines whether diagnostic evidence is conclusive or if the agent must pivot downstream.
"""

from typing import Literal
from app.workflow.state import InvestigationState


def route_evaluation(state: InvestigationState) -> Literal["pivot", "report"]:
    """Conditional edge deciding the next step in the investigation state machine."""
    iteration = state.get("iteration_count", 1)
    max_iter = state.get("max_iterations", 3)
    is_conclusive = state.get("is_conclusive", False)
    confidence = state.get("confidence_score", 0.0)
    visited = state.get("visited_services", [])
    hypotheses = state.get("hypotheses", [])

    # Rule 1: High confidence or conclusive proof -> Generate Final Report
    if is_conclusive or confidence >= 0.85:
        return "report"

    # Rule 2: Budget exhausted -> Terminate and Generate Report with explicit uncertainties
    if iteration >= max_iter:
        return "report"

    # Rule 3: Top hypothesis points to an unvisited downstream dependency -> Pivot!
    if hypotheses:
        top_culprit = hypotheses[0].culprit_service
        if top_culprit not in visited:
            return "pivot"

    # Default fallback
    return "report"
