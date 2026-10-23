from app.core.config import settings
from app.graph.base import GraphStore, DependencyPath
from app.graph.networkx_store import NetworkXGraphStore

_GLOBAL_GRAPH_STORE = None


def get_graph_store() -> GraphStore:
    """Factory to retrieve the configured GraphStore (NetworkX or Neo4j)."""
    global _GLOBAL_GRAPH_STORE
    if _GLOBAL_GRAPH_STORE is None:
        if settings.graph_backend == "neo4j":
            try:
                from app.graph.neo4j_store import Neo4jGraphStore
                _GLOBAL_GRAPH_STORE = Neo4jGraphStore(
                    uri=settings.neo4j_uri,
                    user=settings.neo4j_user,
                    password=settings.neo4j_password
                )
            except Exception:
                # Fallback to in-memory NetworkX if Neo4j daemon is unavailable
                _GLOBAL_GRAPH_STORE = NetworkXGraphStore()
        else:
            _GLOBAL_GRAPH_STORE = NetworkXGraphStore()

    return _GLOBAL_GRAPH_STORE
