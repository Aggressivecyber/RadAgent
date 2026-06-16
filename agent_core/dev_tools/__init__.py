"""Codegen dev tools — file/shell/build tools for agentic build-fix loops.

A :class:`DevToolkit` binds the tools to a project work directory and exposes
the OpenAI function schemas plus an async dispatcher. The agent loop drives it.

These are deliberately separate from ``agent_core.agent_tools`` (the Copilot
orbit-radiation registry): different audience, different sandboxing needs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent_core.dev_tools.files import edit_file, list_files, read_file, search_text, write_file
from agent_core.dev_tools.geant4_docs import search_geant4_docs
from agent_core.dev_tools.schemas import ALL_TOOL_SCHEMAS
from agent_core.dev_tools.shell import build_project, run_bash, run_smoke
from agent_core.dev_tools.web_search import search_web

__all__ = ["DevToolkit", "ALL_TOOL_SCHEMAS"]


class DevToolkit:
    """Bind dev tools to a project directory and dispatch model tool calls.

    Each tool result is recorded in ``self.trace`` for audit (mirrors the
    project's ``tool_calls`` DB discipline).
    """

    def __init__(
        self,
        project_dir: Path,
        *,
        job_id: str = "agentic",
        tool_names: list[str] | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.job_id = job_id
        wanted = set(tool_names) if tool_names else {t["function"]["name"] for t in ALL_TOOL_SCHEMAS}
        self._schemas = [t for t in ALL_TOOL_SCHEMAS if t["function"]["name"] in wanted]
        self.trace: list[dict[str, Any]] = []

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """OpenAI function schemas to send to the model."""
        return self._schemas

    async def dispatch(self, name: str, arguments: Any) -> dict[str, Any]:
        """Execute one tool call. ``arguments`` may be a dict or a JSON string."""
        args = self._parse_arguments(arguments)
        start = time.time()
        try:
            result = await self._invoke(name, args)
        except Exception as exc:  # never let a tool crash kill the loop
            result = {"ok": False, "error": f"Tool {name} crashed: {exc}"}
        record = {
            "tool": name,
            "args": args,
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "latency_ms": round((time.time() - start) * 1000, 1),
            "result": result,
        }
        self.trace.append(record)
        return result

    async def _invoke(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "read_file":
            return read_file(
                self.project_dir,
                str(args.get("path", "")),
                offset=int(args.get("offset") or 1),
                limit=int(args.get("limit") or 200),
            )
        if name == "edit_file":
            return edit_file(
                self.project_dir,
                str(args.get("path", "")),
                str(args.get("old_string", "")),
                str(args.get("new_string", "")),
            )
        if name == "write_file":
            return write_file(
                self.project_dir,
                str(args.get("path", "")),
                str(args.get("content", "")),
            )
        if name == "list_files":
            return list_files(
                self.project_dir,
                str(args.get("glob") or "**/*"),
                max_results=int(args.get("max_results") or 50),
            )
        if name == "search_text":
            return search_text(
                self.project_dir,
                str(args.get("pattern", "")),
                str(args.get("glob") or "**/*"),
                max_results=int(args.get("max_results") or 50),
            )
        if name == "search_geant4_docs":
            return await search_geant4_docs(
                str(args.get("query", "")),
                top_k=int(args.get("top_k") or 5),
            )
        if name == "search_web":
            return await search_web(
                str(args.get("query", "")),
                top_k=int(args.get("top_k") or 5),
            )
        if name == "run_bash":
            return await run_bash(
                self.project_dir,
                str(args.get("command", "")),
                timeout=int(args.get("timeout") or 120),
            )
        if name == "build_project":
            return await build_project(self.project_dir, threads=int(args.get("threads") or 4))
        if name == "run_smoke":
            return await run_smoke(
                self.project_dir,
                events=int(args.get("events") or 5),
                job_id=self.job_id,
            )
        return {"ok": False, "error": f"Unknown tool: {name}"}

    def _invoke_sync_for_test(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Invoke synchronous file-navigation tools in unit tests."""
        if name == "read_file":
            return read_file(
                self.project_dir,
                str(args.get("path", "")),
                offset=int(args.get("offset") or 1),
                limit=int(args.get("limit") or 200),
            )
        if name == "edit_file":
            return edit_file(
                self.project_dir,
                str(args.get("path", "")),
                str(args.get("old_string", "")),
                str(args.get("new_string", "")),
            )
        if name == "write_file":
            return write_file(
                self.project_dir,
                str(args.get("path", "")),
                str(args.get("content", "")),
            )
        if name == "list_files":
            return list_files(
                self.project_dir,
                str(args.get("glob") or "**/*"),
                max_results=int(args.get("max_results") or 50),
            )
        if name == "search_text":
            return search_text(
                self.project_dir,
                str(args.get("pattern", "")),
                str(args.get("glob") or "**/*"),
                max_results=int(args.get("max_results") or 50),
            )
        return {"ok": False, "error": f"Tool is async or unknown: {name}"}

    @staticmethod
    def _parse_arguments(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            if not arguments.strip():
                return {}
            try:
                parsed = json.loads(arguments)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {"_raw_arguments": arguments}
        return {}
