from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.graph.base import GraphStore, DependencyPath
from app.graph import get_graph_store
from app.vector.vector_store import VectorStore
from app.vector.chunker import DocumentChunk, MarkdownChunker
from app.services.telemetry_loader import TelemetryLoader


class HybridRetrievalContext(BaseModel):
    """The synthesized evidence context produced by combining GraphRAG and Vector retrieval."""
    entry_service: str
    reachable_downstream_services: List[str]
    call_paths: List[DependencyPath]
    blast_radius: List[str]
    runbook_chunks: List[DocumentChunk]
    postmortem_chunks: List[DocumentChunk]
    topological_relevance_summary: str


class HybridEngine:
    """Combines GraphRAG dependency traversal with semantic vector search.
    Constrains document retrieval to services on the active downstream call chain,
    eliminating irrelevant noise and preventing LLM hallucination.
    """

    def __init__(
        self,
        graph_store: Optional[GraphStore] = None,
        vector_store: Optional[VectorStore] = None,
        telemetry_loader: Optional[TelemetryLoader] = None
    ):
        self.graph_store = graph_store or get_graph_store()
        self.vector_store = vector_store or VectorStore()
        self.telemetry_loader = telemetry_loader or TelemetryLoader()

        self._initialize_knowledge()

    def _initialize_knowledge(self):
        """Indexes topology in GraphStore and runbooks/postmortems in VectorStore."""
        # 1. Load topology graph
        topo = self.telemetry_loader.get_topology()
        self.graph_store.load_topology(topo.services, topo.dependency_edges)

        # 2. Chunk and index runbooks
        for rb in self.telemetry_loader.get_runbooks():
            chunks = MarkdownChunker.chunk_markdown(
                doc_id=rb["title"],
                title=rb["title"],
                content=rb["content"],
                default_metadata={"document_type": "runbook"}
            )
            self.vector_store.add_chunks(chunks)

        # 3. Chunk and index historical postmortems
        for pm in self.telemetry_loader.get_postmortems():
            chunks = MarkdownChunker.chunk_markdown(
                doc_id=pm["title"],
                title=pm["title"],
                content=pm["content"],
                default_metadata={"document_type": "postmortem"}
            )
            self.vector_store.add_chunks(chunks)

    def retrieve(
        self,
        entry_service: str,
        symptom_query: str,
        max_graph_depth: int = 3,
        top_k_documents: int = 4
    ) -> HybridRetrievalContext:
        """Executes the dual GraphRAG retrieval:
        1. Traverses the graph from entry_service to find reachable downstream dependencies.
        2. Queries semantic vector memory for symptom matches.
        3. Re-ranks documents based on graph topological proximity (GraphRAG fusion).
        """
        # Step 1: Graph Traversal
        downstream_paths = self.graph_store.get_downstream_dependencies(
            entry_service, max_depth=max_graph_depth
        )
        reachable_services = {entry_service}
        for p in downstream_paths:
            reachable_services.update(p.path)

        # Calculate blast radius
        blast_radius = self.graph_store.get_blast_radius(entry_service)

        # Step 2: Semantic Vector Retrieval across all documents
        raw_chunks = self.vector_store.search(symptom_query, top_k=top_k_documents * 3)

        # Step 3: GraphRAG Fusion (Boost documents whose tagged service is on the reachable call path)
        boosted_chunks: List[DocumentChunk] = []
        for chunk in raw_chunks:
            chunk_svc = chunk.metadata.get("service")
            boost = 1.0

            if chunk_svc:
                if chunk_svc in reachable_services:
                    # Service is on the downstream call chain! Boost priority
                    boost = 1.5
                else:
                    # Service is outside the call chain; penalize to reduce noise
                    boost = 0.5

            boosted_chunk = chunk.model_copy()
            boosted_chunk.score = round(chunk.score * boost, 4)
            boosted_chunks.append(boosted_chunk)

        # Sort descending by fused score
        boosted_chunks.sort(key=lambda c: c.score, reverse=True)

        # Separate into runbooks and post-mortems
        runbook_chunks = [
            c for c in boosted_chunks if c.metadata.get("document_type") == "runbook"
        ][:top_k_documents]

        postmortem_chunks = [
            c for c in boosted_chunks if c.metadata.get("document_type") == "postmortem"
        ][:top_k_documents]

        summary = (
            f"GraphRAG traversed {len(downstream_paths)} downstream paths from '{entry_service}'. "
            f"Identified {len(reachable_services)} reachable services on the call chain. "
            f"Fused semantic documents with topological boost."
        )

        return HybridRetrievalContext(
            entry_service=entry_service,
            reachable_downstream_services=sorted(list(reachable_services)),
            call_paths=downstream_paths,
            blast_radius=blast_radius,
            runbook_chunks=runbook_chunks,
            postmortem_chunks=postmortem_chunks,
            topological_relevance_summary=summary
        )
