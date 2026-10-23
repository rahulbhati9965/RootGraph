"""
Unit tests for Phase 4: LangGraph Multi-Agent Investigation Workflow.
Verifies the StateGraph lifecycle, conditional routing, budget enforcement, and final report generation.
"""

import pytest
from app.workflow.engine import InvestigationEngine
from app.workflow.graph import build_investigation_graph
from app.workflow.nodes.evaluator import route_evaluation
from app.workflow.nodes.pivot import pivot_node
from app.schemas.incidents import IncidentCreate, Severity
from app.schemas.investigation import Hypothesis, EvidenceCard


@pytest.fixture
def engine():
    return InvestigationEngine()


def test_langgraph_compilation():
    """Verifies the StateGraph compiles cleanly with all nodes and conditional edges."""
    graph = build_investigation_graph()
    assert graph is not None


def test_end_to_end_investigation(engine: InvestigationEngine):
    """Verifies end-to-end incident investigation workflow on Checkout outage."""
    incident = IncidentCreate(
        title="High Latency & 504 Gateway Timeouts in European Checkout",
        description="Checkout requests timing out when calling downstream payment processing. 504 errors reported.",
        severity=Severity.P0,
        affected_service="checkout-service",
        environment="production"
    )

    report = engine.investigate(incident, incident_id="INC-2024-11-TEST")

    # 1. Verification of structured report schema
    assert report is not None
    assert report.incident_id == "INC-2024-11-TEST"
    assert report.affected_service == "checkout-service"
    assert report.status == "investigated"

    # 2. Root cause localization
    assert report.root_cause_service == "bank-gateway"
    assert report.confidence_score >= 0.85

    # 3. Correlation chain and blast radius
    assert len(report.correlation_chain) >= 2
    assert "api-gateway" in report.blast_radius or len(report.blast_radius) >= 1

    # 4. Verified actionable runbook checks
    assert len(report.recommended_checks) >= 2
    assert any("circuit breaker" in c.lower() or "timeout" in c.lower() for c in report.recommended_checks)

    # 5. Hypotheses validation
    assert len(report.hypotheses) >= 1
    top_h = report.hypotheses[0]
    assert top_h.culprit_service == "bank-gateway"
    assert len(top_h.supporting_evidence) >= 1


def test_evaluator_routing_logic():
    """Verifies the Evaluator node's conditional branching behavior."""
    # Case 1: High confidence & conclusive -> route to report
    state_conclusive = {
        "is_conclusive": True,
        "confidence_score": 0.92,
        "iteration_count": 1,
        "max_iterations": 3,
        "visited_services": ["checkout-service"],
        "hypotheses": [Hypothesis(rank=1, title="Bank Route Flap", culprit_service="bank-gateway", confidence=0.92)]
    }
    assert route_evaluation(state_conclusive) == "report"

    # Case 2: Inconclusive with budget remaining and unvisited culprit -> route to pivot
    state_inconclusive = {
        "is_conclusive": False,
        "confidence_score": 0.65,
        "iteration_count": 1,
        "max_iterations": 3,
        "visited_services": ["checkout-service"],
        "hypotheses": [Hypothesis(rank=1, title="Payment RPC Latency", culprit_service="payment-service", confidence=0.65)]
    }
    assert route_evaluation(state_inconclusive) == "pivot"

    # Case 3: Inconclusive but max iteration reached -> route to report (budget safety)
    state_budget_exhausted = {
        "is_conclusive": False,
        "confidence_score": 0.65,
        "iteration_count": 3,
        "max_iterations": 3,
        "visited_services": ["checkout-service", "payment-service"],
        "hypotheses": [Hypothesis(rank=1, title="Bank Failure", culprit_service="bank-gateway", confidence=0.65)]
    }
    assert route_evaluation(state_budget_exhausted) == "report"


def test_pivot_node_advancement():
    """Verifies pivot node advances focus downstream and increments loop counters."""
    initial_state = {
        "current_focus_service": "checkout-service",
        "visited_services": ["checkout-service"],
        "iteration_count": 1,
        "max_iterations": 3,
        "hypotheses": [Hypothesis(rank=1, title="Downstream Payment Flap", culprit_service="payment-service", confidence=0.7)]
    }

    pivoted = pivot_node(initial_state)

    assert pivoted["current_focus_service"] == "payment-service"
    assert "payment-service" in pivoted["visited_services"]
    assert pivoted["iteration_count"] == 2


def test_investigation_state_traceability(engine: InvestigationEngine):
    """Verifies execution trace logging records all node transitions for observability."""
    state = engine.run_investigation(
        incident_id="INC-TRACE-TEST",
        title="Payment timeouts",
        description="Payment timeouts during high traffic",
        affected_service="checkout-service"
    )

    trace = state.get("execution_trace", [])
    assert len(trace) >= 6

    # Verify key lifecycle milestones in the trace
    trace_text = "\n".join(trace)
    assert "[CLASSIFY]" in trace_text
    assert "[TOPOLOGY]" in trace_text
    assert "[TELEMETRY]" in trace_text
    assert "[DEPLOYMENT]" in trace_text
    assert "[KNOWLEDGE]" in trace_text
    assert "[HYPOTHESIS]" in trace_text
    assert "[REPORT]" in trace_text
