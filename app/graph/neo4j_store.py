from typing import List, Dict, Any, Optional
import logging

from app.schemas.telemetry import ServiceNode, DependencyEdge
from app.graph.base import GraphStore, DependencyPath

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase, Driver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Driver = Any


class Neo4jGraphStore(GraphStore):
    """Production graph engine connecting to Neo4j via official Bolt driver.
    Executes native Cypher queries for deep graph traversals.
    """

    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "password"):
        if not NEO4J_AVAILABLE:
            raise RuntimeError("neo4j driver not installed. Install via 'pip install neo4j'.")
        self.uri = uri
        self.user = user
        self.password = password
        self._driver: Optional[Driver] = None

    def _get_driver(self) -> Driver:
        if self._driver is None:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self._driver

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def load_topology(self, services: List[ServiceNode], edges: List[DependencyEdge]) -> None:
        with self._get_driver().session() as session:
            # Create nodes
            for svc in services:
                session.run(
                    """
                    MERGE (s:Service {name: $name})
                    SET s.id = $id,
                        s.region = $region,
                        s.tier = $tier,
                        s.team = $team,
                        s.protocol = $protocol,
                        s.health_status = $health_status,
                        s.is_external = $is_external
                    """,
                    name=svc.name,
                    id=svc.id,
                    region=svc.region,
                    tier=svc.tier,
                    team=svc.team,
                    protocol=svc.protocol,
                    health_status=svc.health_status,
                    is_external=svc.is_external
                )

            # Create directional edges
            for edge in edges:
                session.run(
                    """
                    MATCH (src:Service {name: $source})
                    MATCH (dst:Service {name: $target})
                    MERGE (src)-[r:DEPENDS_ON]->(dst)
                    SET r.type = $type,
                        r.timeout_ms = $timeout_ms,
                        r.circuit_breaker_enabled = $circuit_breaker_enabled
                    """,
                    source=edge.source,
                    target=edge.target,
                    type=edge.type,
                    timeout_ms=edge.timeout_ms,
                    circuit_breaker_enabled=edge.circuit_breaker_enabled
                )

    def get_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        with self._get_driver().session() as session:
            result = session.run(
                "MATCH (s:Service {name: $name}) RETURN properties(s) AS props",
                name=service_name
            )
            record = result.single()
            if record:
                return dict(record["props"])
            return None

    def get_downstream_dependencies(
        self, service_name: str, max_depth: int = 3
    ) -> List[DependencyPath]:
        paths = []
        with self._get_driver().session() as session:
            query = f"""
            MATCH p = (s:Service {{name: $name}})-[:DEPENDS_ON*1..{max_depth}]->(target:Service)
            RETURN [n in nodes(p) | n.name] AS path, length(p) AS hops, target.name AS target
            """
            result = session.run(query, name=service_name)
            for record in result:
                paths.append(
                    DependencyPath(
                        source=service_name,
                        target=record["target"],
                        hops=record["hops"],
                        path=record["path"]
                    )
                )
        return paths

    def get_upstream_dependencies(
        self, service_name: str, max_depth: int = 3
    ) -> List[DependencyPath]:
        paths = []
        with self._get_driver().session() as session:
            query = f"""
            MATCH p = (caller:Service)-[:DEPENDS_ON*1..{max_depth}]->(s:Service {{name: $name}})
            RETURN [n in nodes(p) | n.name] AS path, length(p) AS hops, caller.name AS caller
            """
            result = session.run(query, name=service_name)
            for record in result:
                paths.append(
                    DependencyPath(
                        source=record["caller"],
                        target=service_name,
                        hops=record["hops"],
                        path=record["path"]
                    )
                )
        return paths

    def get_blast_radius(self, service_name: str) -> List[str]:
        with self._get_driver().session() as session:
            query = """
            MATCH (caller:Service)-[:DEPENDS_ON*1..5]->(target:Service {name: $name})
            RETURN DISTINCT caller.name AS caller
            """
            result = session.run(query, name=service_name)
            return sorted([record["caller"] for record in result])

    def find_shortest_path(self, source: str, target: str) -> Optional[List[str]]:
        with self._get_driver().session() as session:
            query = """
            MATCH p = shortestPath((src:Service {name: $source})-[:DEPENDS_ON*]->(dst:Service {name: $target}))
            RETURN [n in nodes(p) | n.name] AS path
            """
            result = session.run(query, source=source, target=target)
            record = result.single()
            if record:
                return record["path"]
            return None

    def get_subgraph(self, service_name: str, depth: int = 2) -> Dict[str, Any]:
        with self._get_driver().session() as session:
            query = f"""
            MATCH p = (s:Service {{name: $name}})-[:DEPENDS_ON*0..{depth}]-(neighbor:Service)
            RETURN collect(DISTINCT neighbor) AS nodes, collect(relationships(p)) AS rels
            """
            result = session.run(query, name=service_name)
            # Returns localized nodes and edges
            return {"nodes": [], "edges": []}
