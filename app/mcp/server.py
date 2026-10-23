"""
Model Context Protocol (MCP) Diagnostic Server Implementation.
Exposes 8 typed diagnostic tools for autonomous AI incident triage.
Protected by Pydantic schema validation, Circuit Breakers, and Bounded Tool Budgets.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from mcp.server.mcpserver import MCPServer

from app.services.telemetry_loader import TelemetryLoader
from app.graph.networkx_store import NetworkXGraphStore
from app.retrieval.hybrid_engine import HybridEngine
from app.mcp.circuit_breaker import CircuitBreakerManager, CircuitBreakerOpenException
from app.mcp.budget import ToolCallBudget, ToolBudgetExceededError, ToolCallLimitExceededError
from app.mcp.schemas import (
    SearchLogsInput, SearchLogsOutput,
    QueryMetricsInput, QueryMetricsOutput,
    SearchTracesInput, SearchTracesOutput,
    GetServiceDependenciesInput, GetServiceDependenciesOutput,
    SearchRunbooksInput, SearchRunbooksOutput,
    FindSimilarIncidentsInput, FindSimilarIncidentsOutput,
    GetDeploymentHistoryInput, GetDeploymentHistoryOutput,
    SaveInvestigationNoteInput, SaveInvestigationNoteOutput,
)
from app.backend.cache import cache_manager



class DiagnosticServer:
    """Standardized MCP Diagnostic Server for TracePilot."""

    def __init__(
        self,
        telemetry_loader: Optional[TelemetryLoader] = None,
        graph_store: Optional[NetworkXGraphStore] = None,
        hybrid_engine: Optional[HybridEngine] = None,
        circuit_breakers: Optional[CircuitBreakerManager] = None,
        budget: Optional[ToolCallBudget] = None
    ):
        self.loader = telemetry_loader or TelemetryLoader()
        self.graph_store = graph_store or NetworkXGraphStore()
        # Ensure graph store has topology loaded
        topo = self.loader.get_topology()
        self.graph_store.load_topology(topo.services, topo.dependency_edges)

        self.hybrid_engine = hybrid_engine or HybridEngine(
            graph_store=self.graph_store,
            telemetry_loader=self.loader
        )
        self.breakers = circuit_breakers or CircuitBreakerManager(failure_threshold=3, recovery_timeout=30.0)
        self.budget = budget or ToolCallBudget(max_total_calls=25, default_per_tool_limit=10)

        # In-memory investigation notes store: incident_id -> list of note records
        self._investigation_notes: Dict[str, List[Dict[str, Any]]] = {}

        # Underlying official MCP Server
        self.mcp = MCPServer(name="TracePilot-Diagnostics", version="1.0.0")
        self._register_tools()

    def _register_tools(self):
        """Registers all 8 typed tools with the MCP Server."""

        @self.mcp.tool(
            name="search_logs",
            description="Searches correlated distributed logs across microservices with level and substring filters."
        )
        def search_logs_tool(
            service_name: Optional[str] = None,
            trace_id: Optional[str] = None,
            level: Optional[str] = None,
            time_window: Optional[str] = None,
            query: Optional[str] = None,
            limit: int = 50
        ) -> str:
            args = {
                "service_name": service_name,
                "trace_id": trace_id,
                "level": level,
                "time_window": time_window,
                "query": query,
                "limit": limit
            }
            res = self.execute_search_logs(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="query_metrics",
            description="Queries SRE Golden Signal metrics (RED method: latency, error rate, saturation) for a service."
        )
        def query_metrics_tool(
            service_name: str,
            metric_name: str,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            step: Optional[str] = None
        ) -> str:
            args = {
                "service_name": service_name,
                "metric_name": metric_name,
                "start_time": start_time,
                "end_time": end_time,
                "step": step
            }
            res = self.execute_query_metrics(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="search_traces",
            description="Searches distributed OpenTelemetry traces by service, duration threshold, and error status."
        )
        def search_traces_tool(
            service_name: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            min_duration: Optional[int] = None,
            status_filter: Optional[str] = None,
            limit: int = 10
        ) -> str:
            args = {
                "service_name": service_name,
                "start_time": start_time,
                "end_time": end_time,
                "min_duration": min_duration,
                "status_filter": status_filter,
                "limit": limit
            }
            res = self.execute_search_traces(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="get_service_dependencies",
            description="Traverses the architecture graph to find downstream call chains or calculate upstream blast radius."
        )
        def get_service_dependencies_tool(
            service_name: str,
            max_depth: int = 3,
            direction: str = "downstream"
        ) -> str:
            args = {
                "service_name": service_name,
                "max_depth": max_depth,
                "direction": direction
            }
            res = self.execute_get_service_dependencies(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="search_runbooks",
            description="Semantic & GraphRAG retrieval over institutional SRE runbooks with 1.5x topological boosting."
        )
        def search_runbooks_tool(
            query: str,
            service_name: Optional[str] = None,
            limit: int = 3
        ) -> str:
            args = {
                "query": query,
                "service_name": service_name,
                "limit": limit
            }
            res = self.execute_search_runbooks(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="find_similar_incidents",
            description="Searches historical post-mortems for matching outage symptoms, root causes, and lessons learned."
        )
        def find_similar_incidents_tool(
            incident_description: str,
            service_name: Optional[str] = None,
            limit: int = 3
        ) -> str:
            args = {
                "incident_description": incident_description,
                "service_name": service_name,
                "limit": limit
            }
            res = self.execute_find_similar_incidents(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="get_deployment_history",
            description="Retrieves recent software deployments, git commit messages, and configuration changes for a service."
        )
        def get_deployment_history_tool(
            service_name: str,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None
        ) -> str:
            args = {
                "service_name": service_name,
                "start_time": start_time,
                "end_time": end_time
            }
            res = self.execute_get_deployment_history(args)
            return json.dumps(res.model_dump(), default=str)

        @self.mcp.tool(
            name="save_investigation_note",
            description="Records an agent diagnostic observation or hypothesis linked to empirical evidence references."
        )
        def save_investigation_note_tool(
            incident_id: str,
            note: str,
            evidence_references: Optional[List[str]] = None
        ) -> str:
            args = {
                "incident_id": incident_id,
                "note": note,
                "evidence_references": evidence_references or []
            }
            res = self.execute_save_investigation_note(args)
            return json.dumps(res.model_dump(), default=str)

    # --- Tool Execution Implementations ---

    def execute_search_logs(self, raw_args: Dict[str, Any]) -> SearchLogsOutput:
        self.budget.consume("search_logs")
        validated = SearchLogsInput(**raw_args)

        if validated.service_name:
            breaker = self.breakers.get_breaker(validated.service_name)
            breaker.before_execution()

        logs = self.loader.search_logs(
            service=validated.service_name,
            level=validated.level,
            trace_id=validated.trace_id,
            query=validated.query,
            limit=validated.limit
        )

        log_dicts = [log.model_dump() for log in logs]
        return SearchLogsOutput(
            total_found=len(log_dicts),
            service_name=validated.service_name,
            level_filter=validated.level,
            logs=log_dicts
        )

    def execute_query_metrics(self, raw_args: Dict[str, Any]) -> QueryMetricsOutput:
        self.budget.consume("query_metrics")
        validated = QueryMetricsInput(**raw_args)

        breaker = self.breakers.get_breaker(validated.service_name)
        breaker.before_execution()

        def _fetch():
            m = self.loader.get_metrics_summary()
            s = m.summary if m else {}
            r = None
            if m and m.error_rate_by_region:
                r = {reg.region: reg.error_rate_pct for reg in m.error_rate_by_region}
            return {"summary": s, "regions": r}

        metrics_data, _ = cache_manager.get_metrics(
            service_name=validated.service_name,
            metric_name=validated.metric_name,
            fetcher=_fetch,
            ttl_seconds=60,
        )

        return QueryMetricsOutput(
            service_name=validated.service_name,
            metric_name=validated.metric_name,
            summary=metrics_data.get("summary", {}),
            regional_breakdown=metrics_data.get("regions"),
        )

    def execute_search_traces(self, raw_args: Dict[str, Any]) -> SearchTracesOutput:
        self.budget.consume("search_traces")
        validated = SearchTracesInput(**raw_args)

        if validated.service_name:
            breaker = self.breakers.get_breaker(validated.service_name)
            breaker.before_execution()

        traces = self.loader.search_traces(
            service=validated.service_name,
            min_duration=validated.min_duration,
            status_filter=validated.status_filter,
            limit=validated.limit
        )

        trace_dicts = [
            {
                "trace_id": t.trace_id,
                "duration_ms": t.duration_ms,
                "status": t.status,
                "spans_count": t.spans_count,
                "errors_count": t.errors_count,
                "correlation_chain": t.correlation_chain
            }
            for t in traces
        ]

        return SearchTracesOutput(
            total_found=len(trace_dicts),
            traces=trace_dicts
        )

    def execute_get_service_dependencies(self, raw_args: Dict[str, Any]) -> GetServiceDependenciesOutput:
        self.budget.consume("get_service_dependencies")
        validated = GetServiceDependenciesInput(**raw_args)

        def _fetch():
            if validated.direction == "downstream":
                dep_paths = self.graph_store.get_downstream_dependencies(
                    validated.service_name,
                    max_depth=validated.max_depth,
                )
                deps = [p.model_dump() for p in dep_paths]
            else:
                callers = self.graph_store.get_blast_radius(validated.service_name)
                deps = [{"service": c, "relationship": "UPSTREAM_CALLER"} for c in callers]
            blast = self.graph_store.get_blast_radius(validated.service_name)
            return {"dependencies": deps, "blast_radius": blast}

        topo_data, _ = cache_manager.get_topology(
            service_name=validated.service_name,
            direction=validated.direction,
            max_depth=validated.max_depth,
            fetcher=_fetch,
            ttl_seconds=300,
        )

        return GetServiceDependenciesOutput(
            service_name=validated.service_name,
            direction=validated.direction,
            max_depth=validated.max_depth,
            dependencies=topo_data.get("dependencies", []),
            blast_radius=topo_data.get("blast_radius", []),
        )

    def execute_search_runbooks(self, raw_args: Dict[str, Any]) -> SearchRunbooksOutput:
        self.budget.consume("search_runbooks")
        validated = SearchRunbooksInput(**raw_args)

        if validated.service_name:
            context = self.hybrid_engine.retrieve(
                entry_service=validated.service_name,
                symptom_query=validated.query,
                top_k_documents=validated.limit
            )
            chunks = [c.model_dump() for c in context.runbook_chunks]
        else:
            raw_chunks = self.hybrid_engine.vector_store.search(
                query=validated.query,
                top_k=validated.limit
            )
            chunks = [c.model_dump() for c in raw_chunks if c.metadata.get("document_type") == "runbook"]

        return SearchRunbooksOutput(
            query=validated.query,
            total_found=len(chunks),
            top_runbooks=chunks
        )

    def execute_find_similar_incidents(self, raw_args: Dict[str, Any]) -> FindSimilarIncidentsOutput:
        self.budget.consume("find_similar_incidents")
        validated = FindSimilarIncidentsInput(**raw_args)

        if validated.service_name:
            context = self.hybrid_engine.retrieve(
                entry_service=validated.service_name,
                symptom_query=validated.incident_description,
                top_k_documents=validated.limit
            )
            incidents = [c.model_dump() for c in context.postmortem_chunks]
        else:
            raw_chunks = self.hybrid_engine.vector_store.search(
                query=validated.incident_description,
                top_k=validated.limit * 2
            )
            incidents = [c.model_dump() for c in raw_chunks if c.metadata.get("document_type") == "postmortem"][:validated.limit]

        return FindSimilarIncidentsOutput(
            total_found=len(incidents),
            similar_incidents=incidents
        )

    def execute_get_deployment_history(self, raw_args: Dict[str, Any]) -> GetDeploymentHistoryOutput:
        self.budget.consume("get_deployment_history")
        validated = GetDeploymentHistoryInput(**raw_args)

        deployments = self.loader.get_deployments(service=validated.service_name)
        latest = deployments[0] if deployments else None

        return GetDeploymentHistoryOutput(
            service_name=validated.service_name,
            total_deployments=len(deployments),
            latest_deployment=latest,
            deployments=deployments
        )

    def execute_save_investigation_note(self, raw_args: Dict[str, Any]) -> SaveInvestigationNoteOutput:
        self.budget.consume("save_investigation_note")
        validated = SaveInvestigationNoteInput(**raw_args)

        note_id = f"note-{uuid.uuid4().hex[:8]}"
        saved_at = datetime.now(timezone.utc).isoformat()

        record = {
            "note_id": note_id,
            "incident_id": validated.incident_id,
            "note": validated.note,
            "evidence_references": validated.evidence_references,
            "saved_at": saved_at
        }

        if validated.incident_id not in self._investigation_notes:
            self._investigation_notes[validated.incident_id] = []
        self._investigation_notes[validated.incident_id].append(record)

        return SaveInvestigationNoteOutput(
            status="saved",
            incident_id=validated.incident_id,
            note_id=note_id,
            saved_at=saved_at,
            evidence_count=len(validated.evidence_references)
        )

    def get_notes(self, incident_id: str) -> List[Dict[str, Any]]:
        """Returns all investigation notes saved for an incident."""
        return self._investigation_notes.get(incident_id, [])


def create_diagnostic_server() -> DiagnosticServer:
    """Factory creating an initialized DiagnosticServer instance."""
    return DiagnosticServer()
