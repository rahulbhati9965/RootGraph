from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.schemas.telemetry import ServiceNode, DependencyEdge


class DependencyPath(BaseModel):
    """Represents a directional call path through the microservice topology."""
    source: str
    target: str
    hops: int
    path: List[str]
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class GraphStore(ABC):
    """Abstract interface for microservice topology graph operations.
    Allows seamless switching between NetworkX (local standalone) and Neo4j (production).
    """

    @abstractmethod
    def load_topology(self, services: List[ServiceNode], edges: List[DependencyEdge]) -> None:
        """Loads or synchronizes full topology into the graph database."""
        pass

    @abstractmethod
    def get_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves service node metadata."""
        pass

    @abstractmethod
    def get_downstream_dependencies(
        self, service_name: str, max_depth: int = 3
    ) -> List[DependencyPath]:
        """Finds all services called directly or transitively by this service."""
        pass

    @abstractmethod
    def get_upstream_dependencies(
        self, service_name: str, max_depth: int = 3
    ) -> List[DependencyPath]:
        """Finds all upstream services that depend on this service (blast radius)."""
        pass

    @abstractmethod
    def get_blast_radius(self, service_name: str) -> List[str]:
        """Returns all unique services impacted if this service fails."""
        pass

    @abstractmethod
    def find_shortest_path(self, source: str, target: str) -> Optional[List[str]]:
        """Finds the shortest call path between two services."""
        pass

    @abstractmethod
    def get_subgraph(self, service_name: str, depth: int = 2) -> Dict[str, Any]:
        """Extracts localized neighborhood subgraph centered on a service."""
        pass
