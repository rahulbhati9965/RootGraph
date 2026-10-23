"""
Topology Node: Explores microservice dependencies and calculates blast radius.
Invokes the MCP get_service_dependencies tool.
"""

from typing import Dict, Any
from app.workflow.state import InvestigationState
from app.schemas.investigation import EvidenceCard
from app.mcp.runner import MCPDiagnosticRunner


def topology_node(state: InvestigationState) -> Dict[str, Any]:
    runner = MCPDiagnosticRunner()
    current_svc = state.get("current_focus_service", state.get("affected_service", "checkout-service"))

    # Execute MCP tool
    result = runner.call_tool_sync("get_service_dependencies", {
        "service_name": current_svc,
        "max_depth": 3,
        "direction": "downstream"
    })

    dependencies = result.get("dependencies", [])
    blast_radius = result.get("blast_radius", [])

    # Create evidence card
    dep_names = [d.get("target") or d.get("service") for d in dependencies if d.get("target") or d.get("service")]
    finding_msg = (
        f"Graph traversal from '{current_svc}' uncovered {len(dependencies)} downstream call dependencies "
        f"({', '.join(dep_names[:4])}...). Upstream blast radius affects: {', '.join(blast_radius)}."
    )

    card = EvidenceCard(
        source="service_graph",
        reference=f"graph:{current_svc}",
        finding=finding_msg,
        metadata={"dependencies": dep_names, "blast_radius": blast_radius}
    )

    trace_msg = f"[TOPOLOGY] Completed dependency analysis for '{current_svc}'. Discovered {len(dependencies)} paths."

    return {
        "downstream_dependencies": dependencies,
        "blast_radius": blast_radius,
        "evidence_cards": [card],
        "execution_trace": [trace_msg]
    }
