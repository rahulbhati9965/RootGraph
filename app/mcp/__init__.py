"""
TracePilot Model Context Protocol (MCP) Diagnostic Server Package.
Exposes standardized, sandboxed, and circuit-breaker-protected diagnostic tools for AI agents.
"""

from app.mcp.circuit_breaker import CircuitBreaker, CircuitBreakerManager, CircuitState, CircuitBreakerOpenException
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
from app.mcp.server import create_diagnostic_server, DiagnosticServer
from app.mcp.runner import MCPDiagnosticRunner

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerManager",
    "CircuitState",
    "CircuitBreakerOpenException",
    "ToolCallBudget",
    "ToolBudgetExceededError",
    "ToolCallLimitExceededError",
    "DiagnosticServer",
    "create_diagnostic_server",
    "MCPDiagnosticRunner",
]
