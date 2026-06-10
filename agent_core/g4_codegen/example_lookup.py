"""Local Geant4 example lookup tool for codegen agents."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from knowledge_base.geant4.paths import geant4_example_root

from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_CODEGEN

logger = logging.getLogger(__name__)

EXAMPLE_PATHS = {
    "B1": "basic/B1",
    "B2": "basic/B2",
    "B2a": "basic/B2/B2a",
    "B2b": "basic/B2/B2b",
}

TEXT_SUFFIXES = {".cc", ".hh", ".h", ".hpp", ".mac", ".txt", ".in", ".out", ""}


def build_geant4_example_manifest() -> dict[str, Any]:
    """Return available Geant4 example files without embedding file contents."""
    root = _resolve_examples_root()
    manifest: dict[str, Any] = {
        "tool_name": "geant4_example_lookup",
        "status": "available" if root else "unavailable",
        "examples_root": str(root) if root else "",
        "examples": {},
        "request_schema": {
            "example": "B1 | B2 | B2a | B2b",
            "path": "optional path relative to that example",
            "symbol": "optional class/function/token to center the snippet on",
            "query": "optional text query when path is unknown",
            "context_lines": "optional integer, default 36",
            "max_chars": "optional integer, default 6000",
        },
    }
    if root is None:
        manifest["errors"] = ["Geant4 examples root was not found locally"]
        return manifest

    for example_name, relative_root in EXAMPLE_PATHS.items():
        example_root = root / relative_root
        files: list[str] = []
        if example_root.is_dir():
            for path in sorted(example_root.rglob("*")):
                if _is_readable_example_file(path):
                    files.append(str(path.relative_to(example_root)))
        manifest["examples"][example_name] = files
    return manifest


def lookup_geant4_example_snippets(
    requests: list[dict[str, Any]],
    *,
    job_id: str = "",
    module_name: str = "",
    max_results: int = 8,
) -> dict[str, Any]:
    """Execute local snippet lookups requested by a codegen agent."""
    root = _resolve_examples_root()
    result: dict[str, Any] = {
        "tool_name": "geant4_example_lookup",
        "status": "available" if root else "unavailable",
        "module_name": module_name,
        "requests": requests[:max_results],
        "snippets": [],
        "errors": [],
    }
    if root is None:
        result["errors"].append("Geant4 examples root was not found locally")
        _persist_lookup_result(result, job_id, module_name)
        return result

    seen: set[tuple[str, str, str, str]] = set()
    for raw_request in requests[:max_results]:
        if not isinstance(raw_request, dict):
            continue
        request = _normalize_request(raw_request)
        key = (
            request["example"],
            request.get("path", ""),
            request.get("symbol", ""),
            request.get("query", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        snippet, error = _lookup_one(root, request)
        if error:
            result["errors"].append(error)
            continue
        if snippet:
            result["snippets"].append(snippet)

    if not result["snippets"] and not result["errors"]:
        result["errors"].append("No valid lookup requests were provided")
    _persist_lookup_result(result, job_id, module_name)
    return result


def _resolve_examples_root() -> Path | None:
    root = geant4_example_root()
    if root is None or not (root / "basic" / "B2").is_dir():
        return None
    return root


def _is_readable_example_file(path: Path) -> bool:
    return path.is_file() and path.suffix in TEXT_SUFFIXES


def _normalize_request(raw_request: dict[str, Any]) -> dict[str, Any]:
    example = str(raw_request.get("example") or "B2b").strip()
    if example not in EXAMPLE_PATHS:
        example = "B2b"
    context_lines = _bounded_int(raw_request.get("context_lines"), default=36, low=8, high=120)
    max_chars = _bounded_int(raw_request.get("max_chars"), default=6000, low=1200, high=12000)
    return {
        "example": example,
        "path": str(raw_request.get("path") or "").strip(),
        "symbol": str(raw_request.get("symbol") or "").strip(),
        "query": str(raw_request.get("query") or "").strip(),
        "context_lines": context_lines,
        "max_chars": max_chars,
    }


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _lookup_one(root: Path, request: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    example = request["example"]
    example_root = root / EXAMPLE_PATHS[example]
    if not example_root.is_dir():
        return None, f"Example {example} is not available at {example_root}"

    if request.get("path"):
        path = _safe_example_path(example_root, request["path"])
        if path is None:
            return None, f"Unsafe or unavailable example path: {example}/{request['path']}"
        return _snippet_from_path(path, example_root, request), None

    query = request.get("symbol") or request.get("query")
    if not query:
        return None, f"Lookup request for {example} needs path, symbol, or query"
    path = _find_best_file(example_root, query)
    if path is None:
        return None, f"No {example} example file matched query: {query}"
    return _snippet_from_path(path, example_root, request), None


def _safe_example_path(example_root: Path, relative_path: str) -> Path | None:
    candidate = (example_root / relative_path).resolve()
    try:
        candidate.relative_to(example_root.resolve())
    except ValueError:
        return None
    if not _is_readable_example_file(candidate):
        return None
    return candidate


def _find_best_file(example_root: Path, query: str) -> Path | None:
    query_lower = query.lower()
    best: tuple[int, Path] | None = None
    for path in sorted(example_root.rglob("*")):
        if not _is_readable_example_file(path):
            continue
        score = 0
        name_text = str(path.relative_to(example_root)).lower()
        if query_lower in name_text:
            score += 50
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if query_lower in content.lower():
            score += 100
        for token in _query_tokens(query_lower):
            if token in name_text:
                score += 6
            if token in content.lower():
                score += 3
        if score and (best is None or score > best[0]):
            best = (score, path)
    return best[1] if best else None


def _query_tokens(query: str) -> list[str]:
    return [token for token in query.replace("_", " ").split() if len(token) >= 3]


def _snippet_from_path(
    path: Path,
    example_root: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    needle = request.get("symbol") or request.get("query")
    start_line, end_line = _snippet_line_window(
        lines,
        needle=needle,
        context_lines=int(request["context_lines"]),
    )
    snippet = "\n".join(lines[start_line - 1 : end_line])
    max_chars = int(request["max_chars"])
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 34] + "\n[truncated example snippet]"
    return {
        "example": _example_name_for_root(example_root),
        "path": str(path.relative_to(example_root)),
        "line_start": start_line,
        "line_end": end_line,
        "matched": needle or "",
        "content": snippet,
    }


def _snippet_line_window(
    lines: list[str],
    *,
    needle: str,
    context_lines: int,
) -> tuple[int, int]:
    if not lines:
        return 1, 1
    match_index = 0
    if needle:
        needle_lower = needle.lower()
        for index, line in enumerate(lines):
            if needle_lower in line.lower():
                match_index = index
                break
    half_window = max(1, context_lines // 2)
    start_index = max(0, match_index - half_window)
    end_index = min(len(lines), match_index + half_window + 1)
    return start_index + 1, end_index


def _example_name_for_root(example_root: Path) -> str:
    parts = example_root.parts
    if len(parts) >= 1 and parts[-1] in {"B1", "B2a", "B2b", "B2"}:
        return parts[-1]
    return example_root.name


def _persist_lookup_result(result: dict[str, Any], job_id: str, module_name: str) -> None:
    if not job_id:
        return
    try:
        lookup_dir = get_job_dir(job_id) / STAGE_CODEGEN / "example_lookup"
        lookup_dir.mkdir(parents=True, exist_ok=True)
        safe_module = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in module_name)
        path = lookup_dir / f"{safe_module or 'module'}_geant4_examples.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to persist Geant4 example lookup for job %s: %s", job_id, exc)
