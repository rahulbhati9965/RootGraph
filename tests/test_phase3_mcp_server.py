"""
Unit tests for Phase 3: Model Context Protocol (MCP) Diagnostic Server.
Verifies all 8 typed tools, Pydantic validation, Circuit Breakers, and Tool Call Budgets.
"""

import pytest
from app.mcp.runner import MCPDiagnosticRunner
from app.mcp.server import DiagnosticServer
from app.mcp.circuit_breaker import CircuitBreakerOpenException
from app.mcp.budget import ToolCallBudget, ToolBudgetExceededError, ToolCallLimitExceededError
from app.mcp.schemas import SearchLogsInput, QueryMetricsInput


@pytest.fixture
def runner():
    return MCPDiagnosticRunner()


@pytest.fixture
def server():
    return DiagnosticServer()


def test_mcp_list_tools(runner: MCPDiagnosticRunner):
    """Verifies all 8 standardized diagnostic tools are registered in MCP."""
    tools = runner.list_tools_sync()
    tool_names = {t["name"] for t in tools}

    expected_tools = {
        "search_logs",
        "query_metrics",
        "search_traces",
        "get_service_dependencies",
        "search_runbooks",
        "find_similar_incidents",
        "get_deployment_history",
        "save_investigation_note"
    }

    assert expected_tools.issubset(tool_names)
    assert len(tools) == 8


def test_tool_search_logs(runner: MCPDiagnosticRunner):
    """Tool 1: search_logs with level and service filters."""
    result = runner.call_tool_sync("search_logs", {
        "service_name": "bank-gateway",
        "level": "ERROR",
        "limit": 5
    })

    assert result["total_found"] >= 1
    assert result["service_name"] == "bank-gateway"
    assert result["level_filter"] == "ERROR"
    first_log = result["logs"][0]
    assert first_log["service"] == "bank-gateway"
    assert "504" in first_log["message"] or "timeout" in first_log["message"].lower()


def test_tool_query_metrics(runner: MCPDiagnosticRunner):
    """Tool 2: query_metrics returns SRE Golden Signals."""
    result = runner.call_tool_sync("query_metrics", {
        "service_name": "checkout-service",
        "metric_name": "error_rate"
    })

    assert result["service_name"] == "checkout-service"
    assert result["status"] == "success"
    assert "overall_error_rate_pct" in result["summary"]
    assert result["summary"]["overall_error_rate_pct"] == 15.9
    assert result["regional_breakdown"]["eu-central-1"] == 24.6


def test_tool_search_traces(runner: MCPDiagnosticRunner):
    """Tool 3: search_traces finds traces matching duration and error criteria."""
    result = runner.call_tool_sync("search_traces", {
        "status_filter": "ERROR",
        "min_duration": 1000,
        "limit": 5
    })

    assert result["total_found"] >= 1
    first_trace = result["traces"][0]
    assert first_trace["status"] == "ERROR"
    assert first_trace["duration_ms"] >= 1000
    assert len(first_trace["correlation_chain"]) >= 3


def test_tool_get_service_dependencies(runner: MCPDiagnosticRunner):
    """Tool 4: get_service_dependencies computes downstream paths and blast radius."""
    # Downstream traversal
    downstream_res = runner.call_tool_sync("get_service_dependencies", {
        "service_name": "checkout-service",
        "max_depth": 3,
        "direction": "downstream"
    })

    targets = {d["target"] for d in downstream_res["dependencies"]}
    assert "payment-service" in targets
    assert "bank-gateway" in targets

    # Upstream blast radius
    bank_res = runner.call_tool_sync("get_service_dependencies", {
        "service_name": "bank-gateway",
        "direction": "upstream"
    })

    assert "payment-service" in bank_res["blast_radius"]
    assert "checkout-service" in bank_res["blast_radius"]


def test_tool_search_runbooks(runner: MCPDiagnosticRunner):
    """Tool 5: search_runbooks with topological boosting."""
    result = runner.call_tool_sync("search_runbooks", {
        "query": "bank gateway timeout circuit breaker 504",
        "service_name": "payment-service",
        "limit": 2
    })

    assert result["total_found"] >= 1
    top_doc = result["top_runbooks"][0]
    assert "RUNBOOK-PAY-04" in top_doc["title"]
    assert top_doc["metadata"]["service"] == "payment-service"


def test_tool_find_similar_incidents(runner: MCPDiagnosticRunner):
    """Tool 6: find_similar_incidents retrieves historical post-mortems."""
    result = runner.call_tool_sync("find_similar_incidents", {
        "incident_description": "Frankfurt transit route flap causing 504 timeouts",
        "service_name": "bank-gateway",
        "limit": 2
    })

    assert result["total_found"] >= 1
    top_pm = result["similar_incidents"][0]
    assert "INC-2024-11" in top_pm["title"]


def test_tool_get_deployment_history(runner: MCPDiagnosticRunner):
    """Tool 7: get_deployment_history inspects recent git commits and config changes."""
    result = runner.call_tool_sync("get_deployment_history", {
        "service_name": "payment-service"
    })

    assert result["service_name"] == "payment-service"
    assert result["total_deployments"] >= 1
    latest = result["latest_deployment"]
    assert latest["version"] == "v2.4.1"
    assert latest["git_commit"] == "a89f21c"
    assert latest["config_changes"]["BANK_GATEWAY_TIMEOUT_MS"] == 900


def test_tool_save_investigation_note(runner: MCPDiagnosticRunner):
    """Tool 8: save_investigation_note stores evidence-linked hypothesis."""
    result = runner.call_tool_sync("save_investigation_note", {
        "incident_id": "INC-2024-11",
        "note": "Hypothesis: Recent deployment v2.4.1 reduced timeout to 900ms coinciding with bank BGP route flap.",
        "evidence_references": ["span-bank-01", "log-bg-504", "dep-001"]
    })

    assert result["status"] == "saved"
    assert result["incident_id"] == "INC-2024-11"
    assert result["evidence_count"] == 3
    assert result["note_id"].startswith("note-")


def test_safety_pydantic_validation():
    """Safety Guard 1: Pydantic input validation blocks malformed or dangerous inputs."""
    # Invalid characters / SQL injection attempt in service name
    with pytest.raises(Exception):
        SearchLogsInput(service_name="checkout; DROP TABLE logs")

    # Invalid log level
    with pytest.raises(Exception):
        SearchLogsInput(level="CRITICAL_FATAL")

    # Negative limit
    with pytest.raises(Exception):
        SearchLogsInput(limit=-5)

    # Valid input passes
    valid = SearchLogsInput(service_name="payment-service", level="ERROR", limit=10)
    assert valid.service_name == "payment-service"


def test_safety_circuit_breaker(server: DiagnosticServer):
    """Safety Guard 2: Circuit breaker trips after threshold failures and fast-fails."""
    breaker = server.breakers.get_breaker("degraded-external-bank")
    assert breaker.state.value == "CLOSED"

    # Simulate 3 failures
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state.value == "CLOSED"
    breaker.record_failure()
    assert breaker.state.value == "OPEN"

    # Execution against OPEN breaker must immediately raise CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        breaker.before_execution()

    # Reset breaker
    breaker.reset()
    assert breaker.state.value == "CLOSED"


def test_safety_tool_call_budget():
    """Safety Guard 3: Tool budget blocks runaway agent execution loops."""
    budget = ToolCallBudget(max_total_calls=3, default_per_tool_limit=2)

    # First call: OK
    budget.consume("search_logs")
    assert budget.get_usage()["total_calls"] == 1

    # Second call: OK
    budget.consume("search_logs")
    assert budget.get_usage()["total_calls"] == 2

    # Third call to same tool: hits per-tool limit (limit is 2)
    with pytest.raises(ToolCallLimitExceededError):
        budget.consume("search_logs")

    # Call a different tool: hits total budget (limit is 3)
    budget.consume("query_metrics")
    assert budget.get_usage()["total_calls"] == 3

    # Exceed total budget: raises ToolBudgetExceededError
    with pytest.raises(ToolBudgetExceededError):
        budget.consume("search_traces")
