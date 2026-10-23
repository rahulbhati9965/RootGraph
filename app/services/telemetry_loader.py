import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.schemas.telemetry import (
    TopologyData,
    ServiceNode,
    DependencyEdge,
    TraceWaterfall,
    Span,
    LogEntry,
    MetricSummary
)


class TelemetryLoader:
    """Loads and queries synthetic telemetry and scenario data from local JSON/Markdown files."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        else:
            pkg_data = Path(__file__).resolve().parent / "data"
            root_data = Path(__file__).resolve().parent.parent.parent / "data"
            if pkg_data.exists():
                self.data_dir = pkg_data
            else:
                self.data_dir = root_data

        self._topology: Optional[TopologyData] = None
        self._traces: Dict[str, TraceWaterfall] = {}
        self._metrics: Optional[MetricSummary] = None
        self._logs: List[LogEntry] = []
        self._deployments: List[Dict[str, Any]] = []
        self._runbooks: List[Dict[str, str]] = []
        self._postmortems: List[Dict[str, str]] = []

        self._load_all()

    def _load_all(self):
        """Loads all seed datasets into memory."""
        self._load_topology()
        self._load_traces()
        self._load_metrics()
        self._load_logs()
        self._load_deployments()
        self._load_runbooks()
        self._load_postmortems()

    def _load_topology(self):
        topology_file = self.data_dir / "topology" / "services.json"
        if topology_file.exists():
            with open(topology_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._topology = TopologyData(**data)

    def _load_traces(self):
        traces_file = self.data_dir / "telemetry" / "traces.json"
        if traces_file.exists():
            with open(traces_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                trace = TraceWaterfall(**data)
                self._traces[trace.trace_id] = trace

    def _load_metrics(self):
        metrics_file = self.data_dir / "telemetry" / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._metrics = MetricSummary(**data)

    def _load_logs(self):
        logs_file = self.data_dir / "telemetry" / "logs.json"
        if logs_file.exists():
            with open(logs_file, "r", encoding="utf-8") as f:
                entries = json.load(f)
                self._logs = [LogEntry(**entry) for entry in entries]

    def _load_deployments(self):
        dep_file = self.data_dir / "telemetry" / "deployments.json"
        if dep_file.exists():
            with open(dep_file, "r", encoding="utf-8") as f:
                self._deployments = json.load(f)

    def _load_runbooks(self):
        runbooks_dir = self.data_dir / "runbooks"
        if runbooks_dir.exists():
            for file_path in runbooks_dir.glob("*.md"):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self._runbooks.append({
                        "filename": file_path.name,
                        "title": file_path.stem,
                        "content": content
                    })

    def _load_postmortems(self):
        pm_dir = self.data_dir / "postmortems"
        if pm_dir.exists():
            for file_path in pm_dir.glob("*.md"):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self._postmortems.append({
                        "filename": file_path.name,
                        "title": file_path.stem,
                        "content": content
                    })

    # --- Query Methods ---

    def get_topology(self) -> TopologyData:
        if not self._topology:
            raise ValueError("Topology not loaded.")
        return self._topology

    def get_service(self, service_name: str) -> Optional[ServiceNode]:
        if not self._topology:
            return None
        for svc in self._topology.services:
            if svc.name == service_name:
                return svc
        return None

    def get_downstream_dependencies(self, service_name: str) -> List[str]:
        """Finds direct downstream services that the given service calls."""
        if not self._topology:
            return []
        deps = []
        for edge in self._topology.dependency_edges:
            if edge.source == service_name:
                deps.append(edge.target)
        return deps

    def get_upstream_callers(self, service_name: str) -> List[str]:
        """Finds upstream services that call into this service."""
        if not self._topology:
            return []
        callers = []
        for edge in self._topology.dependency_edges:
            if edge.target == service_name:
                callers.append(edge.source)
        return callers

    def get_trace(self, trace_id: str) -> Optional[TraceWaterfall]:
        return self._traces.get(trace_id)

    def get_critical_path(self, trace_id: str) -> List[Span]:
        """Returns spans that are on the critical path (status!=OK or is_slow=True)."""
        trace = self.get_trace(trace_id)
        if not trace:
            return []
        return [span for span in trace.spans if span.status in ["ERROR", "WARN"] or span.is_slow]

    def search_logs(
        self,
        service: Optional[str] = None,
        level: Optional[str] = None,
        trace_id: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50
    ) -> List[LogEntry]:
        """Searches structured logs by service, log level, trace ID, or free-text query."""
        results = []
        for log in self._logs:
            if service and log.service != service:
                continue
            if level and log.level != level:
                continue
            if trace_id and log.trace_id != trace_id:
                continue
            if query and query.lower() not in log.message.lower():
                continue
            results.append(log)
            if len(results) >= limit:
                break
        return results

    def get_metrics_summary(self) -> Optional[MetricSummary]:
        return self._metrics

    def get_runbooks(self) -> List[Dict[str, str]]:
        return self._runbooks

    def get_postmortems(self) -> List[Dict[str, str]]:
        return self._postmortems

    def get_deployments(self, service: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns deployment history, optionally filtered by service."""
        if not service:
            return self._deployments
        return [d for d in self._deployments if d.get("service") == service]

    def search_traces(
        self,
        service: Optional[str] = None,
        min_duration: Optional[int] = None,
        status_filter: Optional[str] = None,
        limit: int = 10
    ) -> List[TraceWaterfall]:
        """Searches traces matching criteria."""
        results = []
        for trace in self._traces.values():
            if status_filter and trace.status.upper() != status_filter.upper():
                continue
            if min_duration is not None and trace.duration_ms < min_duration:
                continue
            if service:
                service_in_trace = any(s.service_name == service for s in trace.spans)
                if not service_in_trace:
                    continue
            results.append(trace)
            if len(results) >= limit:
                break
        return results
