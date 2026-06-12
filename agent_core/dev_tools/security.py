"""Path-safety helpers shared by dev tools.

All dev tools operate inside a project work directory. These helpers keep file
operations inside that jail: reject absolute paths, parent traversal, symlinks
escaping the root, etc.
"""

from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """Raised when a requested path would leave the project work directory."""


def resolve_within(root: Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` against ``root`` and enforce it stays inside.

    Rejects absolute paths, ``..`` traversal, and resolved paths that escape
    the project root (including via symlinks).
    """
    root = root.resolve()
    raw = str(relative_path).strip()
    if not raw:
        raise PathEscapeError("Empty path.")
    if raw.startswith("/"):
        raise PathEscapeError(f"Absolute paths are not allowed: {raw!r}")
    candidate = (root / raw).resolve()
    if root != candidate and root not in candidate.parents:
        raise PathEscapeError(f"Path escapes project root: {raw!r}")
    return candidate
