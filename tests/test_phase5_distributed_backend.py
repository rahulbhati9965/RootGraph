"""
Unit and Integration Tests for Phase 5: Distributed Systems Backend.
Tests SHA-256 idempotency deduplication, distributed atomic leases,
event streaming (consumer groups, ACK, DLQ), background worker execution,
and FastAPI REST API endpoints.
"""

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.backend.idempotency import IdempotencyManager, idempotency_manager
from app.backend.streaming import MemoryEventStream, StreamMessage
from app.backend.repository import IncidentRepository, repository
from app.backend.cache import cache_manager, CacheAsideManager
from app.backend.worker import BackgroundInvestigationWorker
from app.schemas.incidents import IncidentCreate, Severity, IncidentStatus
from app.schemas.investigation import InvestigationStatus


@pytest.fixture(autouse=True)
def clean_state():
    """Cleans up in-memory states before each test."""
    idempotency_manager.clear()
    repository.clear()
    cache_manager.clear()
    yield
    idempotency_manager.clear()
    repository.clear()
    cache_manager.clear()


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


# ---------------------------------------------------------
# 1. Idempotency & Deduplication Tests
# ---------------------------------------------------------

def test_fingerprint_determinism():
    """Verifies SHA-256 fingerprint is deterministic within the same time bucket."""
    fp1 = IdempotencyManager.compute_fingerprint(
        service="checkout-service",
        title="High Latency 504",
        environment="production",
        time_bucket_minutes=5,
    )
    fp2 = IdempotencyManager.compute_fingerprint(
        service="checkout-service",
        title="High Latency 504",
        environment="production",
        time_bucket_minutes=5,
    )
    fp_diff = IdempotencyManager.compute_fingerprint(
        service="payment-service",
        title="High Latency 504",
        environment="production",
        time_bucket_minutes=5,
    )

    assert fp1 == fp2
    assert fp1 != fp_diff
    assert len(fp1) == 64  # Valid SHA-256 hex string


def test_alert_storm_deduplication():
    """Verifies that an alert storm (burst of 10 identical alerts) is collapsed to 1 novel event."""
    manager = IdempotencyManager(default_ttl_seconds=300)
    fp = manager.compute_fingerprint("checkout-service", "Timeout Alert")

    # First event is novel
    is_dup1, existing1 = manager.check_and_register(fp, record={"alert_id": 1})
    assert is_dup1 is False
    assert existing1 is None

    # Next 9 events in storm are recognized as duplicates
    for i in range(2, 11):
        is_dup, existing = manager.check_and_register(fp, record={"alert_id": i})
        assert is_dup is True
        assert existing == {"alert_id": 1}


# ---------------------------------------------------------
# 2. Distributed Atomic Leases Tests
# ---------------------------------------------------------

def test_atomic_lease_concurrency():
    """Verifies mutual exclusion on incident investigations via atomic leases."""
    manager = IdempotencyManager()
    res_id = "INC-TEST-001"

    # Worker 1 acquires lease
    assert manager.acquire_lease(res_id, lease_seconds=10.0) is True

    # Worker 2 attempts to acquire lease on same incident -> rejected
    assert manager.acquire_lease(res_id, lease_seconds=10.0) is False

    # Worker 1 finishes and releases lease
    manager.release_lease(res_id)

    # Worker 2 can now acquire the lease
    assert manager.acquire_lease(res_id, lease_seconds=10.0) is True


# ---------------------------------------------------------
# 3. Event Streaming & DLQ Tests
# ---------------------------------------------------------

def test_memory_event_stream_ack_and_pel():
    """Verifies consumer groups, pending entry tracking, and ACK semantics."""
    stream = MemoryEventStream()
    stream_name = "test:stream"
    group = "test-group"
    consumer = "test-consumer"

    # Publish 3 messages
    m1 = stream.publish(stream_name, {"seq": 1})
    m2 = stream.publish(stream_name, {"seq": 2})
    m3 = stream.publish(stream_name, {"seq": 3})

    # Consume batch
    messages = stream.consume(stream_name, group, consumer, count=2)
    assert len(messages) == 2
    assert messages[0].message_id == m1
    assert messages[1].message_id == m2

    # Verify pending state
    group_key = f"{stream_name}:{group}"
    assert m1 in stream._pending[group_key]
    assert m2 in stream._pending[group_key]

    # Ack message 1
    assert stream.ack(stream_name, group, m1) is True
    assert m1 not in stream._pending[group_key]
    assert m2 in stream._pending[group_key]


def test_dead_letter_queue_routing():
    """Verifies failed messages are safely routed to DLQ with error annotations."""
    stream = MemoryEventStream()
    stream_name = "orders:stream"
    group = "order-processors"

    msg_id = stream.publish(stream_name, {"order_id": "ORD-999"})
    stream.consume(stream_name, group, "worker-1", count=1)

    # Route to DLQ
    dlq_id = stream.dead_letter(
        stream=stream_name,
        group=group,
        message_id=msg_id,
        error="Downstream RPC timeout after 3 retries",
    )

    assert dlq_id == msg_id
    dlq_messages = stream.get_dlq_messages(stream_name)
    assert len(dlq_messages) == 1
    assert dlq_messages[0].message_id == msg_id
    assert dlq_messages[0].error == "Downstream RPC timeout after 3 retries"


# ---------------------------------------------------------
# 4. Background Worker Execution Tests
# ---------------------------------------------------------

def test_worker_process_batch():
    """Verifies background worker consumes alerts from stream and executes investigations."""
    stream = MemoryEventStream()
    worker = BackgroundInvestigationWorker(
        stream=stream,
        stream_name="stream:alerts",
        group_name="test-workers",
        consumer_name="worker-unit-test",
    )

    # Create incident in repository
    incident = repository.create_incident(
        IncidentCreate(
            title="High Latency & 504 Gateway Timeouts in European Checkout",
            description="Checkout requests timing out when calling downstream payment processing.",
            severity=Severity.P0,
            affected_service="checkout-service",
            environment="production",
        )
    )

    # Publish investigation trigger event
    stream.publish("stream:alerts", {"event": "alert_received", "incident_id": incident.id})

    # Worker processes batch
    processed_count = worker.process_batch(count=5)
    assert processed_count == 1

    # Verify repository updates
    updated_inc = repository.get_incident(incident.id)
    assert updated_inc.status == IncidentStatus.REPORT_READY

    report = repository.get_report(incident.id)
    assert report is not None
    assert report.incident_id == incident.id
    assert report.root_cause_service == "bank-gateway"
    assert report.confidence_score >= 0.85


# ---------------------------------------------------------
# 5. FastAPI REST API Endpoint Tests
# ---------------------------------------------------------

def test_api_health(client: TestClient):
    """Verifies /api/v1/health returns 200 OK and service metadata."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "stream_backend" in data


def test_api_alert_ingestion_and_deduplication(client: TestClient):
    """Verifies POST /api/v1/alerts ingests novel alerts (201) and deduplicates burst replays (200)."""
    payload = {
        "title": "Database Connection Pool Starvation",
        "description": "Exhausted connections on postgres pool.",
        "severity": "P1",
        "affected_service": "payment-service",
        "environment": "production",
    }

    # 1. First alert -> 201 Created
    res1 = client.post("/api/v1/alerts", json=payload)
    assert res1.status_code == 201
    assert res1.headers.get("X-Idempotent-Replay") == "false"
    data1 = res1.json()
    assert data1["status"] == "created"
    assert data1["idempotent_replay"] is False
    incident_id = data1["incident"]["id"]

    # 2. Second alert in storm -> 200 OK with X-Idempotent-Replay: true
    res2 = client.post("/api/v1/alerts", json=payload)
    assert res2.status_code == 200
    assert res2.headers.get("X-Idempotent-Replay") == "true"
    data2 = res2.json()
    assert data2["status"] == "deduplicated"
    assert data2["idempotent_replay"] is True
    assert data2["incident"]["id"] == incident_id


def test_api_incident_crud_and_sync_investigation(client: TestClient):
    """Verifies incident creation, listing, synchronous investigation, and report retrieval."""
    # 1. Create incident
    create_res = client.post(
        "/api/v1/incidents",
        json={
            "title": "High Latency & 504 Gateway Timeouts in European Checkout",
            "description": "504 errors reported on checkout path.",
            "severity": "P0",
            "affected_service": "checkout-service",
            "environment": "production",
        },
    )
    assert create_res.status_code == 201
    inc = create_res.json()
    inc_id = inc["id"]

    # 2. List incidents
    list_res = client.get("/api/v1/incidents?service=checkout-service")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Trigger synchronous investigation
    inv_res = client.post(f"/api/v1/incidents/{inc_id}/investigations?sync=true")
    assert inv_res.status_code == 200
    inv_data = inv_res.json()
    assert inv_data["status"] == "COMPLETED"
    assert "report" in inv_data
    assert inv_data["report"]["root_cause_service"] == "bank-gateway"

    # 4. Fetch investigation record
    inv_id = inv_data["investigation_id"]
    get_inv = client.get(f"/api/v1/investigations/{inv_id}")
    assert get_inv.status_code == 200
    assert get_inv.json()["status"] == "COMPLETED"

    # 5. Fetch SRE report
    report_res = client.get(f"/api/v1/incidents/{inc_id}/report")
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["incident_id"] == inc_id
    assert report_data["root_cause_service"] == "bank-gateway"
    assert len(report_data["hypotheses"]) >= 1


# ---------------------------------------------------------
# 6. Redis / Memory Cache-Aside Lookups Tests
# ---------------------------------------------------------

def test_cache_aside_topology_and_metrics():
    """Verifies Cache-Aside pattern for high-frequency topology and SRE metrics lookups."""
    fetch_counter = {"topology": 0, "metrics": 0}

    def fetch_topology():
        fetch_counter["topology"] += 1
        return {"service": "checkout-service", "downstream": ["payment-service", "inventory-service"]}

    def fetch_metrics():
        fetch_counter["metrics"] += 1
        return {"error_rate_pct": 14.2, "p95_latency_ms": 2800}

    # 1. First call -> Cache MISS (triggers authoritative fetcher)
    topo1, is_hit1 = cache_manager.get_topology("checkout-service", "downstream", max_depth=2, fetcher=fetch_topology)
    assert is_hit1 is False
    assert fetch_counter["topology"] == 1
    assert topo1["service"] == "checkout-service"

    # 2. Second call -> Cache HIT (returns cached data without calling fetcher)
    topo2, is_hit2 = cache_manager.get_topology("checkout-service", "downstream", max_depth=2, fetcher=fetch_topology)
    assert is_hit2 is True
    assert fetch_counter["topology"] == 1  # Fetcher not invoked again!
    assert topo2 == topo1

    # 3. Metrics Cache-Aside
    met1, is_mhit1 = cache_manager.get_metrics("payment-service", "p95_latency", fetcher=fetch_metrics)
    assert is_mhit1 is False
    assert fetch_counter["metrics"] == 1

    met2, is_mhit2 = cache_manager.get_metrics("payment-service", "p95_latency", fetcher=fetch_metrics)
    assert is_mhit2 is True
    assert fetch_counter["metrics"] == 1  # Fetcher not invoked again!

    # 4. Cache Telemetry Stats
    stats = cache_manager.stats
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["total_queries"] == 4
    assert stats["hit_rate_pct"] == 50.0

