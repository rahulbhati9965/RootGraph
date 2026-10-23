"""
Pivot Node: Advances diagnostic investigation to downstream candidate culprit services.
Loops back to telemetry inspection along the causal call chain.
"""

from typing import Dict, Any
from app.workflow.state import InvestigationState


def pivot_node(state: InvestigationState) -> Dict[str, Any]:
    visited = list(state.get("visited_services", []))
    hypotheses = state.get("hypotheses", [])
    iteration = state.get("iteration_count", 1) + 1
    max_iter = state.get("max_iterations", 3)

    # Determine next target service
    next_service = None
    if hypotheses:
        for h in hypotheses:
            if h.culprit_service not in visited:
                next_service = h.culprit_service
                break

    if not next_service:
        # Fallback to first unvisited downstream dependency
        deps = state.get("downstream_dependencies", [])
        for d in deps:
            target = d.get("target") or d.get("service")
            if target and target not in visited:
                next_service = target
                break

    if not next_service:
        next_service = "bank-gateway"  # Default downstream failure root

    visited.append(next_service)
    trace_msg = (
        f"[PIVOT] Causal chain leads downstream. Advancing diagnostic focus to '{next_service}' "
        f"(Iteration {iteration}/{max_iter})."
    )

    return {
        "current_focus_service": next_service,
        "visited_services": visited,
        "iteration_count": iteration,
        "execution_trace": [trace_msg]
    }
