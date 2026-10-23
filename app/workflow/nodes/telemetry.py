"""
Telemetry Node: Gathers empirical distributed traces, logs, and golden signal metrics.
Dispatches MCP search_traces, search_logs, and query_metrics tools.
"""

from typing import Dict, Any, List
from app.workflow.state import InvestigationState
from app.schemas.investigation import EvidenceCard
from app.mcp.runner import MCPDiagnosticRunner


def telemetry_node(state: InvestigationState) -> Dict[str, Any]:
    runner = MCPDiagnosticRunner()
    current_svc = state.get("current_focus_service", state.get("affected_service", "checkout-service"))
    new_evidence: List[EvidenceCard] = []

    # 1. Search Traces
    trace_res = runner.call_tool_sync("search_traces", {
        "service_name": current_svc,
        "status_filter": "ERROR",
        "limit": 3
    })
    traces = trace_res.get("traces", [])
    correlation_chain = state.get("correlation_id")

    if traces:
        top_trace = traces[0]
        correlation_chain = " > ".join(top_trace.get("correlation_chain", []))
        card_trace = EvidenceCard(
            source="trace_span",
            reference=f"trace:{top_trace.get('trace_id')}",
            finding=(
                f"Trace {top_trace.get('trace_id')} failed with duration {top_trace.get('duration_ms')}ms "
                f"across {top_trace.get('spans_count')} spans. Correlation path: {correlation_chain}."
            ),
            metadata=top_trace
        )
        new_evidence.append(card_trace)

    # 2. Search Correlated Logs
    log_res = runner.call_tool_sync("search_logs", {
        "service_name": current_svc,
        "level": "ERROR",
        "limit": 5
    })
    logs = log_res.get("logs", [])
    if logs:
        err_msg = logs[0].get("message", "Unknown error")
        card_log = EvidenceCard(
            source="log_entry",
            reference=f"log:{logs[0].get('timestamp', 'recent')}",
            finding=f"Observed ERROR in service '{current_svc}': \"{err_msg}\"",
            metadata=logs[0]
        )
        new_evidence.append(card_log)

    # 3. Query Golden Signal Metrics
    metric_res = runner.call_tool_sync("query_metrics", {
        "service_name": current_svc,
        "metric_name": "error_rate"
    })
    summary = metric_res.get("summary", {})
    regions = metric_res.get("regional_breakdown", {})
    if summary:
        overall_err = summary.get("overall_error_rate_pct", 0)
        p95_lat = summary.get("p95_latency_ms", 0)
        highest_region = max(regions.items(), key=lambda x: x[1]) if regions else ("unknown", 0)

        card_metric = EvidenceCard(
            source="metric_anomaly",
            reference=f"metric:{current_svc}:error_rate",
            finding=(
                f"Golden Signals degraded: Overall error rate at {overall_err}%, P95 latency at {p95_lat}ms. "
                f"Worst-hit region: {highest_region[0]} ({highest_region[1]}% failure rate)."
            ),
            metadata={"summary": summary, "regions": regions}
        )
        new_evidence.append(card_metric)

    trace_msg = (
        f"[TELEMETRY] Gathered {len(new_evidence)} empirical evidence cards for '{current_svc}' "
        f"({len(traces)} error traces, {len(logs)} logs, SRE metrics)."
    )

    return {
        "traces_inspected": traces,
        "logs_inspected": logs,
        "metrics_inspected": metric_res,
        "correlation_id": correlation_chain,
        "evidence_cards": new_evidence,
        "execution_trace": [trace_msg]
    }
