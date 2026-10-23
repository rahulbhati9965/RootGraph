"""
LangGraph Investigation StateGraph Definition.
Constructs the multi-agent cyclic graph with deterministic branching and Evaluator-Optimizer feedback loops.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from app.workflow.state import InvestigationState
from app.workflow.nodes.classify import classify_node
from app.workflow.nodes.topology import topology_node
from app.workflow.nodes.telemetry import telemetry_node
from app.workflow.nodes.deployment import deployment_node
from app.workflow.nodes.knowledge import knowledge_node
from app.workflow.nodes.hypothesize import hypothesize_node
from app.workflow.nodes.evaluator import route_evaluation
from app.workflow.nodes.pivot import pivot_node
from app.workflow.nodes.report import report_node


def build_investigation_graph() -> CompiledStateGraph:
    """Builds and compiles the full LangGraph incident investigation workflow."""
    builder = StateGraph(InvestigationState)

    # 1. Register Nodes
    builder.add_node("classify", classify_node)
    builder.add_node("topology", topology_node)
    builder.add_node("telemetry", telemetry_node)
    builder.add_node("deployment", deployment_node)
    builder.add_node("knowledge", knowledge_node)
    builder.add_node("hypothesize", hypothesize_node)
    builder.add_node("pivot", pivot_node)
    builder.add_node("report", report_node)

    # 2. Add Fixed Edges
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "topology")
    builder.add_edge("topology", "telemetry")
    builder.add_edge("telemetry", "deployment")
    builder.add_edge("deployment", "knowledge")
    builder.add_edge("knowledge", "hypothesize")

    # 3. Add Evaluator Conditional Branching
    builder.add_conditional_edges(
        source="hypothesize",
        path=route_evaluation,
        path_map={
            "pivot": "pivot",
            "report": "report"
        }
    )

    # 4. Loop back from pivot to telemetry
    builder.add_edge("pivot", "telemetry")

    # 5. Terminal edge
    builder.add_edge("report", END)

    # Compile the graph
    return builder.compile()
