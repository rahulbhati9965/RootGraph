"""
LangGraph Investigation State Definition.
Holds the evolving diagnostic context, evidence cards, hypotheses, and iteration counters.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from app.schemas.investigation import EvidenceCard, Hypothesis, InvestigationReport


def append_list(existing: List[Any], new_items: List[Any]) -> List[Any]:
    """Reducer that appends new items while avoiding duplicates if possible."""
    if not existing:
        return list(new_items)
    if not new_items:
        return list(existing)
    return existing + [item for item in new_items if item not in existing]


class InvestigationState(TypedDict, total=False):
    """The central state dictionary passed between LangGraph nodes."""

    # Incident identification
    incident_id: str
    title: str
    description: str
    affected_service: str
    current_focus_service: str
    severity: str
    environment: str
    correlation_id: Optional[str]

    # Graph Topology & Reachability
    downstream_dependencies: List[Dict[str, Any]]
    blast_radius: List[str]
    visited_services: List[str]

    # Empirical Evidence Accumulators (Appended across nodes)
    evidence_cards: Annotated[List[EvidenceCard], operator.add]
    execution_trace: Annotated[List[str], operator.add]

    # Inspection Results
    traces_inspected: List[Dict[str, Any]]
    logs_inspected: List[Dict[str, Any]]
    metrics_inspected: Dict[str, Any]
    deployments_inspected: List[Dict[str, Any]]

    # Knowledge & Runbooks
    retrieved_runbooks: List[Dict[str, Any]]
    retrieved_postmortems: List[Dict[str, Any]]

    # Reasoning & Evaluator-Optimizer
    hypotheses: List[Hypothesis]
    is_conclusive: bool
    confidence_score: float
    iteration_count: int
    max_iterations: int
    status: str

    # Final Output
    final_report: Optional[InvestigationReport]
