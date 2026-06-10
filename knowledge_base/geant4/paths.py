"""Path helpers for Geant4 knowledge-base tooling."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_EXAMPLE_ROOTS = (
    "/usr/local/geant4/share/Geant4/examples",
    "/usr/share/Geant4/examples",
    "/opt/geant4/share/Geant4/examples",
)


def geant4_example_root() -> Path | None:
    """Resolve the local Geant4 examples root, if available."""
    env_root = os.getenv("RADAGENT_GEANT4_EXAMPLES_ROOT", "").strip()
    candidates = [env_root] if env_root else []
    candidates.extend(DEFAULT_EXAMPLE_ROOTS)
    for raw_path in candidates:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if (path / "basic").is_dir():
            return path
    return None
