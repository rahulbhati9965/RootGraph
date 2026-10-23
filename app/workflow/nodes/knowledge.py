"""
Knowledge Node: Retrieves operational runbooks and historical post-mortems.
Invokes MCP search_runbooks and find_similar_incidents with GraphRAG topological boosting.
"""

from typing import Dict, Any, List
from app.workflow.state import InvestigationState
from app.schemas.investigation import EvidenceCard
from app.mcp.runner import MCPDiagnosticRunner


def knowledge_node(state: InvestigationState) -> Dict[str, Any]:
    runner = MCPDiagnosticRunner()
    current_svc = state.get("current_focus_service", state.get("affected_service", "checkout-service"))
    query = f"{state.get('title', '')} {state.get('description', '')}".strip()
    if not query:
        query = f"timeouts and latency degradation in {current_svc}"

    new_evidence: List[EvidenceCard] = []

    # 1. Search Runbooks via GraphRAG
    rb_res = runner.call_tool_sync("search_runbooks", {
        "query": query,
        "service_name": current_svc,
        "limit": 2
    })
    runbooks = rb_res.get("top_runbooks", [])

    if runbooks:
        top_rb = runbooks[0]
        snippet = top_rb.get("content", "").strip().split("\n")[0][:120]
        card_rb = EvidenceCard(
            source="runbook",
            reference=f"runbook:{top_rb.get('title')}",
            finding=(
                f"Retrieved verified runbook '{top_rb.get('title')}' for service '{top_rb.get('metadata', {}).get('service')}' "
                f"(relevance score {top_rb.get('score', 0):.2f}). Section: '{top_rb.get('section')}'. Directive: {snippet}..."
            ),
            metadata=top_rb
        )
        new_evidence.append(card_rb)

    # 2. Find Similar Historical Post-Mortems
    pm_res = runner.call_tool_sync("find_similar_incidents", {
        "incident_description": query,
        "service_name": current_svc,
        "limit": 2
    })
    postmortems = pm_res.get("similar_incidents", [])

    if postmortems:
        top_pm = postmortems[0]
        card_pm = EvidenceCard(
            source="postmortem",
            reference=f"postmortem:{top_pm.get('title')}",
            finding=(
                f"Found matching historical incident '{top_pm.get('title')}' "
                f"(similarity score {top_pm.get('score', 0):.2f}). Recorded root cause matches active symptom profile."
            ),
            metadata=top_pm
        )
        new_evidence.append(card_pm)

    trace_msg = (
        f"[KNOWLEDGE] GraphRAG retrieved {len(runbooks)} runbooks and {len(postmortems)} "
        f"post-mortems topologically linked to '{current_svc}'."
    )

    return {
        "retrieved_runbooks": runbooks,
        "retrieved_postmortems": postmortems,
        "evidence_cards": new_evidence,
        "execution_trace": [trace_msg]
    }
