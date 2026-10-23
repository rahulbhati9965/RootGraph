"""
MCP Diagnostic Runner and Python Client Adapter.
Allows seamless tool calling from LangGraph agents, tests, or CLI runners.
"""

import asyncio
from typing import Dict, Any, List, Optional
from app.mcp.server import DiagnosticServer, create_diagnostic_server


class MCPDiagnosticRunner:
    """Convenient Python client adapter for executing MCP diagnostic tools."""

    def __init__(self, server: Optional[DiagnosticServer] = None):
        self.server = server or create_diagnostic_server()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Lists all registered tools with schemas from the MCP server."""
        mcp_tools = await self.server.mcp.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": getattr(t, "inputSchema", getattr(t, "input_schema", {}))
            }
            for t in mcp_tools
        ]

    def list_tools_sync(self) -> List[Dict[str, Any]]:
        """Synchronous wrapper for list_tools."""
        return asyncio.run(self.list_tools())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a tool via the MCP server protocol and returns structured result."""
        result = await self.server.mcp.call_tool(name=name, arguments=arguments)

        # Parse text content from MCP result
        if result.content and len(result.content) > 0:
            first_content = result.content[0]
            text = getattr(first_content, "text", "")
            try:
                import json
                return json.loads(text)
            except Exception:
                return {"raw_text": text}

        return {"status": "empty_response"}

    def call_tool_sync(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for call_tool."""
        return asyncio.run(self.call_tool(name=name, arguments=arguments))

    # --- Convenience inspection & safety methods ---

    def get_budget_usage(self) -> Dict[str, Any]:
        return self.server.budget.get_usage()

    def reset_budget(self):
        self.server.budget.reset()

    def get_breaker_state(self, service_name: str) -> str:
        return self.server.breakers.get_breaker(service_name).state.value

    def trip_breaker(self, service_name: str):
        self.server.breakers.get_breaker(service_name).trip()

    def reset_breaker(self, service_name: str):
        self.server.breakers.get_breaker(service_name).reset()
