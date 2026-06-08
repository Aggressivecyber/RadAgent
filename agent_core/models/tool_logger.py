"""Tool call logger — tracks LLM and tool invocations.

Provides a simple event system for logging tool calls.
The REPL subscribes to display calls in real-time.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """A single tool call record."""

    tool_name: str
    task: str
    tier: str
    provider: str
    model_name: str
    metadata: dict[str, Any]
    start_time: float
    end_time: float = 0.0
    latency_ms: float = 0.0
    success: bool = True
    error: str | None = None
    content_length: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "task": self.task,
            "tier": self.tier,
            "provider": self.provider,
            "model_name": self.model_name,
            "metadata": self.metadata,
            "latency_ms": round(self.latency_ms, 1),
            "success": self.success,
            "error": self.error,
            "content_length": self.content_length,
        }


class ToolCallLogger:
    """Singleton logger for tool calls.

    Supports:
    - Recording tool calls to a list
    - Writing to a JSONL log file
    - Notifying subscribers (e.g. REPL) of new calls
    """

    def __init__(self) -> None:
        self._records: list[ToolCallRecord] = []
        self._subscribers: list[Callable[[ToolCallRecord], None]] = []
        self._log_file: Path | None = None

    def set_log_file(self, path: Path) -> None:
        """Set a JSONL log file for persistent logging."""
        self._log_file = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, callback: Callable[[ToolCallRecord], None]) -> None:
        """Subscribe to tool call events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[ToolCallRecord], None]) -> None:
        """Unsubscribe from tool call events."""
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def record(self, call: ToolCallRecord) -> None:
        """Record a tool call and notify subscribers."""
        self._records.append(call)

        # Write to log file
        if self._log_file:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(call.to_dict(), ensure_ascii=False) + "\n")
            except OSError as exc:
                logger.warning("Failed to write tool log: %s", exc)

        # Notify subscribers
        for sub in self._subscribers:
            try:
                sub(call)
            except Exception as exc:
                logger.warning("Tool call subscriber error: %s", exc)

    def get_records(self) -> list[ToolCallRecord]:
        """Get all recorded tool calls."""
        return list(self._records)

    def get_records_since(self, since: float) -> list[ToolCallRecord]:
        """Get tool calls since a timestamp."""
        return [r for r in self._records if r.start_time >= since]

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()

    def summary(self) -> dict[str, Any]:
        """Get a summary of tool calls."""
        if not self._records:
            return {"total_calls": 0}

        by_task: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        total_latency = 0.0
        errors = 0

        for r in self._records:
            by_task[r.task] = by_task.get(r.task, 0) + 1
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
            total_latency += r.latency_ms
            if not r.success:
                errors += 1

        return {
            "total_calls": len(self._records),
            "by_task": by_task,
            "by_provider": by_provider,
            "total_latency_ms": round(total_latency, 1),
            "avg_latency_ms": round(total_latency / len(self._records), 1),
            "errors": errors,
        }


# Global singleton
_logger: ToolCallLogger | None = None


def get_tool_logger() -> ToolCallLogger:
    """Get the global tool call logger."""
    global _logger
    if _logger is None:
        _logger = ToolCallLogger()
    return _logger


def reset_tool_logger() -> None:
    """Reset the global tool call logger (for testing)."""
    global _logger
    _logger = None
