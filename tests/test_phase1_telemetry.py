import pytest
from pathlib import Path
from app.services.telemetry_loader import TelemetryLoader


@pytest.fixture
def loader():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    return TelemetryLoader(data_dir=data_dir)


def test_topology_services_loaded(loader: TelemetryLoader):
    topology = loader.get_topology()
    assert len(topology.services) == 12
    assert topology.environment == "production"

    checkout = loader.get_service("checkout-service")
    assert checkout is not None
    assert checkout.region == "us-east-1"
    assert checkout.tier == "tier-0"
    assert "payment-service" in checkout.dependencies

    bank_gateway = loader.get_service("bank-gateway")
    assert bank_gateway is not None
    assert bank_gateway.region == "eu-central-1"
    assert bank_gateway.is_external is True


def test_dependency_traversal(loader: TelemetryLoader):
    # Verify downstream call chain: checkout-service -> payment-service -> bank-gateway
    checkout_deps = loader.get_downstream_dependencies("checkout-service")
    assert "payment-service" in checkout_deps
    assert "inventory-service" in checkout_deps

    payment_deps = loader.get_downstream_dependencies("payment-service")
    assert "bank-gateway" in payment_deps
    assert "fraud-service" in payment_deps

    # Verify upstream reverse lookup
    bank_callers = loader.get_upstream_callers("bank-gateway")
    assert "payment-service" in bank_callers


def test_trace_waterfall_critical_path(loader: TelemetryLoader):
    trace_id = "1-6653af2e-17c4f8b3e4a2c6d7e8f9a0b1"
    trace = loader.get_trace(trace_id)
    assert trace is not None
    assert trace.duration_ms == 2348
    assert trace.status == "ERROR"
    assert trace.correlation_chain == ["a1b2c3d4", "b2c3d4e5", "c3d4e5f6", "d4e5f607"]

    # Critical path should isolate the slow / error spans
    critical_path = loader.get_critical_path(trace_id)
    critical_services = [s.service_name for s in critical_path]
    assert "checkout-service" in critical_services
    assert "payment-service" in critical_services
    assert "bank-gateway" in critical_services

    # Inspect bank-gateway span details
    bank_span = next(s for s in trace.spans if s.service_name == "bank-gateway")
    assert bank_span.status_code == 504
    assert bank_span.region == "eu-central-1"
    assert bank_span.tags["error.type"] == "GatewayTimeoutException"


def test_golden_signals_metrics(loader: TelemetryLoader):
    metrics = loader.get_metrics_summary()
    assert metrics is not None
    assert metrics.summary["overall_error_rate_pct"] == 15.9
    assert metrics.summary["p95_latency_ms"] == 2800

    # Regional error breakdown
    regions = {r.region: r.error_rate_pct for r in metrics.error_rate_by_region}
    assert regions["eu-central-1"] == 24.6
    assert regions["eu-west-1"] == 18.9

    # Service error breakdown
    services = {s.service: s.error_rate_pct for s in metrics.top_services_by_error_rate}
    assert services["checkout-service"] == 32.1
    assert services["payment-service"] == 28.7


def test_correlated_logs_search(loader: TelemetryLoader):
    # Search error logs for bank-gateway
    bank_logs = loader.search_logs(service="bank-gateway", level="ERROR")
    assert len(bank_logs) >= 1
    assert "504 Gateway Timeout" in bank_logs[0].message
    assert bank_logs[0].correlation_id == "d4e5f607"

    # Search error logs for payment-service
    payment_logs = loader.search_logs(service="payment-service", level="ERROR")
    assert len(payment_logs) >= 1
    assert "Payment gateway timeout" in payment_logs[0].message
    assert payment_logs[0].correlation_id == "c3d4e5f6"


def test_runbooks_and_postmortems_loaded(loader: TelemetryLoader):
    runbooks = loader.get_runbooks()
    assert len(runbooks) >= 1
    pay_runbook = next(r for r in runbooks if "RUNBOOK-PAY-04" in r["title"])
    assert "payment-service" in pay_runbook["content"]
    assert "circuit breaker" in pay_runbook["content"].lower()

    postmortems = loader.get_postmortems()
    assert len(postmortems) >= 1
    flap_pm = next(p for p in postmortems if "INC-2024-11" in p["title"])
    assert "BGP route flap" in flap_pm["content"]
