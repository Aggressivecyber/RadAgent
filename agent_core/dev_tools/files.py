"""File dev tools: read_file, edit_file, write_file — all jailed to project_dir."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_core.dev_tools.security import PathEscapeError, resolve_within

DEFAULT_READ_LIMIT = 200


def read_file(project_dir: Path, path: str, *, offset: int = 1, limit: int = DEFAULT_READ_LIMIT) -> dict[str, Any]:
    """Read a file with 1-based line numbers, capped to ``limit`` lines."""
    try:
        target = resolve_within(project_dir, path)
    except PathEscapeError as exc:
        return {"ok": False, "error": str(exc)}

    if not target.exists():
        return {"ok": False, "error": f"File not found: {path}"}
    if target.is_dir():
        return {"ok": False, "error": f"Path is a directory: {path}"}

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": f"Read failed: {exc}"}

    lines = text.splitlines()
    start = max(1, int(offset))
    end = min(len(lines), start + max(1, int(limit)) - 1)
    rendered = "\n".join(f"{i:>5}: {lines[i-1]}" for i in range(start, end + 1))
    return {
        "ok": True,
        "path": path,
        "total_lines": len(lines),
        "shown_range": [start, end],
        "content": rendered,
    }


def edit_file(project_dir: Path, path: str, old_string: str, new_string: str) -> dict[str, Any]:
    """Replace the unique occurrence of ``old_string`` with ``new_string``.

    Refuses if ``old_string`` is absent or appears more than once — the model
    must add context to make the match unique. This is the key safety property.
    """
    if old_string == "":
        return {"ok": False, "error": "old_string must be non-empty."}
    try:
        target = resolve_within(project_dir, path)
    except PathEscapeError as exc:
        return {"ok": False, "error": str(exc)}

    if not target.exists():
        return {"ok": False, "error": f"File not found: {path}"}

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": f"Read failed: {exc}"}

    occurrences = text.count(old_string)
    if occurrences == 0:
        # Show the closest lines so the model can correct old_string without a
        # separate read_file round-trip (saves a turn).
        hint = _closest_lines(text, old_string)
        return {
            "ok": False,
            "error": "old_string not found. The actual current text near your match is below — copy it exactly.",
            "nearby_lines": hint,
        }
    if occurrences > 1:
        return {
            "ok": False,
            "error": (
                f"old_string matches {occurrences} places; it must be unique. "
                "Include more surrounding context lines."
            ),
        }

    updated = text.replace(old_string, new_string)
    target.write_text(updated, encoding="utf-8")
    return {
        "ok": True,
        "path": path,
        "bytes_written": len(updated),
    }


def write_file(project_dir: Path, path: str, content: str) -> dict[str, Any]:
    """Overwrite (or create) a project file with full content."""
    try:
        target = resolve_within(project_dir, path)
    except PathEscapeError as exc:
        return {"ok": False, "error": str(exc)}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "bytes_written": len(content)}


def _closest_lines(text: str, old_string: str, *, context: int = 6) -> str:
    """Return the lines around the best partial match for old_string.

    Helps the model self-correct a failed edit in the same turn instead of
    spending another read_file round-trip.
    """
    lines = text.splitlines()
    needle = old_string.strip().splitlines()[0] if old_string.strip() else ""
    if not needle:
        # Fallback: show the head of the file.
        return "\n".join(f"{i+1}: {ln}" for i, ln in enumerate(lines[:context]))
    best_idx, best_score = 0, 0
    for i, ln in enumerate(lines):
        # Token-overlap score (words in common).
        overlap = sum(1 for w in needle.split() if w and w in ln)
        if overlap > best_score:
            best_score, best_idx = overlap, i
    start = max(0, best_idx - context // 2)
    end = min(len(lines), start + context)
    return "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))
