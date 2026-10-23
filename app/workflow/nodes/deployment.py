"""
Deployment Node: Inspects recent CI/CD deployments and configuration changes.
Invokes the MCP get_deployment_history tool.
"""

from typing import Dict, Any, List
from app.workflow.state import InvestigationState
from app.schemas.investigation import EvidenceCard
from app.mcp.runner import MCPDiagnosticRunner


def deployment_node(state: InvestigationState) -> Dict[str, Any]:
    runner = MCPDiagnosticRunner()
    current_svc = state.get("current_focus_service", state.get("affected_service", "checkout-service"))
    new_evidence: List[EvidenceCard] = []

    dep_res = runner.call_tool_sync("get_deployment_history", {
        "service_name": current_svc
    })
    deployments = dep_res.get("deployments", [])
    latest = dep_res.get("latest_deployment")

    if latest:
        config_changes = latest.get("config_changes", {})
        config_desc = f"with configuration change: {config_changes}" if config_changes else "with zero configuration deltas"
        finding_msg = (
            f"Service '{current_svc}' had recent deployment {latest.get('version')} "
            f"(commit {latest.get('git_commit')}) by {latest.get('deployed_by')} {config_desc}. "
            f"Commit message: \"{latest.get('commit_message')}\"."
        )

        card = EvidenceCard(
            source="deployment",
            reference=f"commit:{latest.get('git_commit')}",
            finding=finding_msg,
            metadata=latest
        )
        new_evidence.append(card)

    trace_msg = f"[DEPLOYMENT] Checked deployment history for '{current_svc}': Found {len(deployments)} releases."

    return {
        "deployments_inspected": deployments,
        "evidence_cards": new_evidence,
        "execution_trace": [trace_msg]
    }
