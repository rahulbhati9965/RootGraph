import networkx as nx
from typing import List, Dict, Any, Optional

from app.schemas.telemetry import ServiceNode, DependencyEdge
from app.graph.base import GraphStore, DependencyPath


class NetworkXGraphStore(GraphStore):
    """In-memory, high-performance graph engine powered by NetworkX.
    Runs 100% locally with zero external containers, providing identical BFS/DFS
    and shortest-path algorithms to Neo4j.
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    def load_topology(self, services: List[ServiceNode], edges: List[DependencyEdge]) -> None:
        self.graph.clear()

        # Add service nodes with rich metadata
        for svc in services:
            self.graph.add_node(
                svc.name,
                id=svc.id,
                name=svc.name,
                region=svc.region,
                tier=svc.tier,
                team=svc.team,
                protocol=svc.protocol,
                health_status=svc.health_status,
                is_external=svc.is_external
            )

        # Add directed dependency edges with communication attributes
        for edge in edges:
            self.graph.add_edge(
                edge.source,
                edge.target,
                type=edge.type,
                timeout_ms=edge.timeout_ms,
                circuit_breaker_enabled=edge.circuit_breaker_enabled
            )

    def get_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        if service_name in self.graph:
            data = dict(self.graph.nodes[service_name])
            data["name"] = service_name
            return data
        return None

    def get_downstream_dependencies(
        self, service_name: str, max_depth: int = 3
    ) -> List[DependencyPath]:
        """Traverses outgoing call edges (BFS) up to max_depth."""
        if service_name not in self.graph:
            return []

        paths: List[DependencyPath] = []
        visited = set()
        queue = [([service_name], 0)]

        while queue:
            current_path, depth = queue.pop(0)
            current_node = current_path[-1]

            if depth > 0:
                edge_list = []
                for i in range(len(current_path) - 1):
                    src, dst = current_path[i], current_path[i + 1]
                    edge_data = dict(self.graph.get_edge_data(src, dst, default={}))
                    edge_data["source"] = src
                    edge_data["target"] = dst
                    edge_list.append(edge_data)

                paths.append(
                    DependencyPath(
                        source=service_name,
                        target=current_node,
                        hops=depth,
                        path=current_path,
                        edges=edge_list
                    )
                )

            if depth < max_depth:
                for neighbor in self.graph.successors(current_node):
                    if neighbor not in current_path:  # Prevent cyclic loops
                        queue.append((current_path + [neighbor], depth + 1))

        return paths

    def get_upstream_dependencies(
        self, service_name: str, max_depth: int = 3
    ) -> List[DependencyPath]:
        """Traverses incoming call edges (reverse BFS) to identify caller chains."""
        if service_name not in self.graph:
            return []

        paths: List[DependencyPath] = []
        queue = [([service_name], 0)]

        while queue:
            current_path, depth = queue.pop(0)
            current_node = current_path[-1]

            if depth > 0:
                edge_list = []
                # In reverse path: current_node -> ... -> service_name
                # Physical call is: current_node calls next node
                actual_call_chain = list(reversed(current_path))
                for i in range(len(actual_call_chain) - 1):
                    src, dst = actual_call_chain[i], actual_call_chain[i + 1]
                    edge_data = dict(self.graph.get_edge_data(src, dst, default={}))
                    edge_data["source"] = src
                    edge_data["target"] = dst
                    edge_list.append(edge_data)

                paths.append(
                    DependencyPath(
                        source=current_node,
                        target=service_name,
                        hops=depth,
                        path=actual_call_chain,
                        edges=edge_list
                    )
                )

            if depth < max_depth:
                for predecessor in self.graph.predecessors(current_node):
                    if predecessor not in current_path:
                        queue.append((current_path + [predecessor], depth + 1))

        return paths

    def get_blast_radius(self, service_name: str) -> List[str]:
        """Calculates all upstream services that depend directly or indirectly on this service."""
        if service_name not in self.graph:
            return []

        # In a directed graph, if B fails, all ancestors (who call B) are impacted.
        # nx.ancestors returns all nodes that have a directed path to service_name.
        impacted_nodes = nx.ancestors(self.graph, service_name)
        return sorted(list(impacted_nodes))

    def find_shortest_path(self, source: str, target: str) -> Optional[List[str]]:
        try:
            return nx.shortest_path(self.graph, source=source, target=target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_subgraph(self, service_name: str, depth: int = 2) -> Dict[str, Any]:
        """Extracts an ego-network containing both upstream callers and downstream dependencies."""
        if service_name not in self.graph:
            return {"nodes": [], "edges": []}

        subgraph_nodes = {service_name}

        # Collect downstream
        down_paths = self.get_downstream_dependencies(service_name, max_depth=depth)
        for p in down_paths:
            subgraph_nodes.update(p.path)

        # Collect upstream
        up_paths = self.get_upstream_dependencies(service_name, max_depth=depth)
        for p in up_paths:
            subgraph_nodes.update(p.path)

        sub_g = self.graph.subgraph(subgraph_nodes)

        nodes = [{"name": n, **dict(sub_g.nodes[n])} for n in sub_g.nodes()]
        edges = [
            {"source": u, "target": v, **dict(sub_g.get_edge_data(u, v))}
            for u, v in sub_g.edges()
        ]

        return {"nodes": nodes, "edges": edges}
