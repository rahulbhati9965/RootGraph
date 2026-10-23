"""
Tool Call Budget and Rate Limiting for AI Agents.
Prevents infinite loops, runaway spend, and LLM tool thrashing.
"""

import threading
from typing import Dict, Any, Optional


class ToolBudgetExceededError(Exception):
    """Raised when an AI investigation session exceeds its total allowed tool calls."""
    def __init__(self, current: int, max_budget: int):
        super().__init__(
            f"Investigation tool budget exceeded: {current}/{max_budget} calls used. "
            f"Halting tool execution to prevent runaway LLM loop."
        )
        self.current = current
        self.max_budget = max_budget


class ToolCallLimitExceededError(Exception):
    """Raised when a specific tool is invoked more times than permitted in one session."""
    def __init__(self, tool_name: str, count: int, max_limit: int):
        super().__init__(
            f"Tool limit exceeded for '{tool_name}': {count}/{max_limit} calls used. "
            f"Agent must diversify diagnostic strategy."
        )
        self.tool_name = tool_name
        self.count = count
        self.max_limit = max_limit


class ToolCallBudget:
    """Tracks and enforces tool call quotas for an agent session."""

    def __init__(
        self,
        max_total_calls: int = 25,
        default_per_tool_limit: int = 10,
        custom_per_tool_limits: Optional[Dict[str, int]] = None
    ):
        self.max_total_calls = max_total_calls
        self.default_per_tool_limit = default_per_tool_limit
        self.custom_per_tool_limits = custom_per_tool_limits or {}

        self._total_calls = 0
        self._tool_counts: Dict[str, int] = {}
        self._lock = threading.Lock()

    def consume(self, tool_name: str):
        """Validates and increments the budget. Raises error if limits exceeded."""
        with self._lock:
            # Check global budget
            if self._total_calls >= self.max_total_calls:
                raise ToolBudgetExceededError(self._total_calls, self.max_total_calls)

            # Check per-tool limit
            limit = self.custom_per_tool_limits.get(tool_name, self.default_per_tool_limit)
            current_tool_calls = self._tool_counts.get(tool_name, 0)
            if current_tool_calls >= limit:
                raise ToolCallLimitExceededError(tool_name, current_tool_calls, limit)

            # Increment counters
            self._total_calls += 1
            self._tool_counts[tool_name] = current_tool_calls + 1

    def get_usage(self) -> Dict[str, Any]:
        """Returns snapshot of current usage and remaining quotas."""
        with self._lock:
            return {
                "total_calls": self._total_calls,
                "max_total_calls": self.max_total_calls,
                "remaining_budget": max(0, self.max_total_calls - self._total_calls),
                "calls_by_tool": dict(self._tool_counts)
            }

    def reset(self):
        """Resets the session budget."""
        with self._lock:
            self._total_calls = 0
            self._tool_counts.clear()
