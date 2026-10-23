"""
Unit and Integration Tests for Phase 6: Observability, Quantitative Benchmarks & Interactive UI.
Tests OpenTelemetry correlation propagation, Evaluation Harness metrics (Precision/Recall/MTTD),
and Cockpit UI API feeds.
"""

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.core.telemetry import (
    inject_correlation_headers,
    extract_correlation_headers,
    trace_step,
    telemetry_recorder,
    generate_trace_id,
    generate_correlation_id,
)
from eval_harness import EvaluationHarness, BENCHMARK_SCENARIOS


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------
# 1. OpenTelemetry & Correlation Tests
# ---------------------------------------------------------

def test_opentelemetry_correlation_headers():
    """Verifies injection and extraction of W3C TraceContext and X-Correlation-ID."""
    headers = {}
    injected = inject_correlation_headers(headers)

    assert "X-Correlation-ID" in injected
    assert "traceparent" in injected
    assert injected["traceparent"].startswith("00-")

    extracted = extract_correlation_headers(injected)
    assert len(extracted["trace_id"]) == 32
    assert extracted["correlation_id"] == injected["X-Correlation-ID"]


def test_trace_step_decorator():
    """Verifies @trace_step records execution spans with timing and status."""
    telemetry_recorder.clear()

    @trace_step("test_node_execution", span_type="langgraph_node")
    def sample_node(x: int):
        return x * 2

    res = sample_node(21)
    assert res == 42

    spans = telemetry_recorder._spans
    assert len(spans) >= 1
    span = spans[-1]
    assert span.name == "test_node_execution"
    assert span.span_type == "langgraph_node"
    assert span.status == "OK"
    assert span.duration_ms is not None
    assert span.duration_ms >= 0


def test_api_correlation_middleware(client: TestClient):
    """Verifies incoming HTTP requests are decorated with X-Correlation-ID and traceparent."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert "X-Correlation-ID" in res.headers
    assert "traceparent" in res.headers
    assert res.headers["traceparent"].startswith("00-")


# ---------------------------------------------------------
# 2. Evaluation Benchmark Suite Tests
# ---------------------------------------------------------

def test_eval_harness_execution():
    """Verifies the automated evaluation suite achieves high accuracy and MTTD reduction."""
    harness = EvaluationHarness()
    results = harness.run_suite()

    # 1. Total Scenarios
    assert results.total_scenarios == 3

    # 2. Accuracy & Precision/Recall
    assert results.precision >= 0.90
    assert results.recall >= 0.90
    assert results.f1_score >= 0.90
    assert results.correct_localizations == 3

    # 3. Simulated MTTD Reduction (>65% reduction per resume bullet)
    assert results.average_mttd_reduction_pct >= 65.0
    assert results.average_tracepilot_mttd_seconds < 5.0

    # 4. Token Accounting
    assert results.total_tokens_consumed > 5000


# ---------------------------------------------------------
# 3. Cockpit Dashboard Endpoints Tests
# ---------------------------------------------------------

def test_cockpit_html_endpoint(client: TestClient):
    """Verifies /cockpit serves the interactive visual cockpit dashboard."""
    res = client.get("/cockpit")
    assert res.status_code == 200
    assert "DEBUG DISTRIBUTED" in res.text
    assert "Distributed Trace Waterfall" in res.text


def test_cockpit_telemetry_data(client: TestClient):
    """Verifies /api/v1/cockpit/data returns full structured telemetry bundle."""
    res = client.get("/api/v1/cockpit/data")
    assert res.status_code == 200
    data = res.json()

    assert data["incident_id"] == "INC-2024-11"
    assert data["spans_count"] == 48
    assert len(data["waterfall_spans"]) >= 10
    assert len(data["top_services"]) >= 4
    assert len(data["topology_nodes"]) >= 6
    assert len(data["correlation_chain"]) >= 3


def test_cockpit_remediation_execution(client: TestClient):
    """Verifies /api/v1/cockpit/remediate executes one-click SRE runbook action."""
    payload = {
        "action": "Trip Circuit Breaker",
        "service": "bank-gateway",
        "incident_id": "INC-2024-11",
    }
    res = client.post("/api/v1/cockpit/remediate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "applied"
    assert "Trip Circuit Breaker" in data["message"]
