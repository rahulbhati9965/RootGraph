import pytest
from pathlib import Path

from app.services.telemetry_loader import TelemetryLoader
from app.graph.networkx_store import NetworkXGraphStore
from app.vector.chunker import MarkdownChunker
from app.vector.vector_store import VectorStore
from app.retrieval.hybrid_engine import HybridEngine


@pytest.fixture
def telemetry_loader():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    return TelemetryLoader(data_dir=data_dir)


@pytest.fixture
def graph_store(telemetry_loader):
    store = NetworkXGraphStore()
    topo = telemetry_loader.get_topology()
    store.load_topology(topo.services, topo.dependency_edges)
    return store


def test_networkx_graph_store_traversal(graph_store: NetworkXGraphStore):
    # Downstream dependencies from checkout-service
    downstream = graph_store.get_downstream_dependencies("checkout-service", max_depth=3)
    target_names = {p.target for p in downstream}

    # Direct dependencies
    assert "payment-service" in target_names
    assert "inventory-service" in target_names
    assert "pricing-service" in target_names

    # Multi-hop transitive dependencies (2 hops away)
    assert "bank-gateway" in target_names
    assert "fraud-service" in target_names

    # Verify exact path to bank-gateway
    bank_path = next(p for p in downstream if p.target == "bank-gateway")
    assert bank_path.hops == 2
    assert bank_path.path == ["checkout-service", "payment-service", "bank-gateway"]

    # Verify shortest path
    shortest = graph_store.find_shortest_path("checkout-service", "bank-gateway")
    assert shortest == ["checkout-service", "payment-service", "bank-gateway"]


def test_blast_radius_calculation(graph_store: NetworkXGraphStore):
    # If bank-gateway in Frankfurt fails, who is impacted upstream?
    blast_radius = graph_store.get_blast_radius("bank-gateway")

    assert "payment-service" in blast_radius
    assert "checkout-service" in blast_radius
    assert "api-gateway" in blast_radius


def test_markdown_chunker(telemetry_loader: TelemetryLoader):
    runbooks = telemetry_loader.get_runbooks()
    pay_runbook = next(r for r in runbooks if "RUNBOOK-PAY-04" in r["title"])

    chunks = MarkdownChunker.chunk_markdown(
        doc_id=pay_runbook["title"],
        title=pay_runbook["title"],
        content=pay_runbook["content"]
    )

    assert len(chunks) >= 2
    # Verify metadata extraction
    assert chunks[0].metadata.get("service") == "payment-service"

    # Verify code block preservation in mitigation chunk
    mitigation_chunk = next(c for c in chunks if "Mitigation" in c.section)
    assert "circuit-breaker trip" in mitigation_chunk.content


def test_vector_store_semantic_search(telemetry_loader: TelemetryLoader):
    vector_store = VectorStore()

    # Index runbooks
    for rb in telemetry_loader.get_runbooks():
        chunks = MarkdownChunker.chunk_markdown(
            doc_id=rb["title"], title=rb["title"], content=rb["content"]
        )
        vector_store.add_chunks(chunks)

    # Search with natural language symptom query
    results = vector_store.search("payment gateway timeout 504 circuit breaker", top_k=2)
    assert len(results) > 0
    top_result = results[0]
    assert "RUNBOOK-PAY-04" in top_result.document_id
    assert top_result.score > 0.5


def test_hybrid_graphrag_fusion(telemetry_loader: TelemetryLoader):
    engine = HybridEngine(telemetry_loader=telemetry_loader)

    # Given alert on checkout-service with bank gateway symptoms
    context = engine.retrieve(
        entry_service="checkout-service",
        symptom_query="bank gateway latency 504 timeout circuit breaker",
        max_graph_depth=3,
        top_k_documents=3
    )

    # 1. Verify Graph Context
    assert context.entry_service == "checkout-service"
    assert "bank-gateway" in context.reachable_downstream_services
    assert "payment-service" in context.reachable_downstream_services

    # 2. Verify Blast Radius
    assert "api-gateway" in context.blast_radius

    # 3. Verify GraphRAG Fused Documents
    assert len(context.runbook_chunks) > 0
    top_runbook = context.runbook_chunks[0]
    assert "RUNBOOK-PAY-04" in top_runbook.document_id
    assert top_runbook.metadata.get("service") == "payment-service"

    # 4. Verify Past Incident Post-Mortem Match
    assert len(context.postmortem_chunks) > 0
    top_postmortem = context.postmortem_chunks[0]
    assert "INC-2024-11" in top_postmortem.document_id
