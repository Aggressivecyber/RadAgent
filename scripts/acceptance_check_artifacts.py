#!/usr/bin/env python3
"""Acceptance artifact checks for a real RadAgent job.

The default target is the real full-graph job directory. The script fails
on missing artifacts; it never treats sample/dev artifacts as acceptance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_core.workspace.paths import (  # noqa: E402
    GEANT4_PROJECT_DIRNAME,
    STAGE_CODEGEN,
    STAGE_GATE_VALIDATION,
    STAGE_PATCH,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(name: str, condition: bool, failures: list[str], detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    if not condition:
        failures.append(f"{name}: {detail}")


def _resolve_artifact_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        default="simulation_workspace/jobs/real_full_graph",
        help="Real job artifact directory to validate.",
    )
    args = parser.parse_args()

    artifact_dir = _resolve_artifact_dir(args.artifact_dir)
    failures: list[str] = []

    print(f"=== Artifact Acceptance Check: {artifact_dir} ===")
    _check("artifact directory exists", artifact_dir.is_dir(), failures)

    g4_dir = artifact_dir / STAGE_PATCH / GEANT4_PROJECT_DIRNAME
    codegen_dir = artifact_dir / STAGE_CODEGEN
    gate_dir = artifact_dir / STAGE_GATE_VALIDATION

    _check(f"{STAGE_PATCH}/{GEANT4_PROJECT_DIRNAME} exists", g4_dir.is_dir(), failures)
    _check("CMakeLists.txt exists", (g4_dir / "CMakeLists.txt").is_file(), failures)
    _check("main.cc exists", (g4_dir / "main.cc").is_file(), failures)
    _check(
        "src/*.cc exists",
        any((g4_dir / "src").glob("*.cc")) if g4_dir.exists() else False,
        failures,
    )
    _check(
        "include/*.hh exists",
        any((g4_dir / "include").glob("*.hh")) if g4_dir.exists() else False,
        failures,
    )

    patch_path = codegen_dir / "proposed_patch.json"
    _check("proposed_patch.json exists", patch_path.is_file(), failures)
    if patch_path.is_file():
        patch = _load_json(patch_path)
        changed_files = patch.get("changed_files", [])
        _check("proposed_patch changed_files non-empty", bool(changed_files), failures)
        for idx, file_entry in enumerate(changed_files):
            prefix = f"changed_files[{idx}]"
            _check(f"{prefix} has new_content", "new_content" in file_entry, failures)
            _check(f"{prefix} has no content", "content" not in file_entry, failures)
            _check(f"{prefix} has module_name", bool(file_entry.get("module_name")), failures)
            _check(f"{prefix} has generated_by", bool(file_entry.get("generated_by")), failures)
            _check(f"{prefix} has zone", bool(file_entry.get("zone")), failures)

    gate_path = gate_dir / "gate_results.json"
    _check("gate_results.json exists", gate_path.is_file(), failures)
    if gate_path.is_file():
        gates = _load_json(gate_path)
        failed = [g for g in gates if g.get("status") in {"fail", "block", "blocked"}]
        critical_skipped = [
            g
            for g in gates
            if g.get("status") in {"skip", "skipped"} and g.get("critical", True) is not False
        ]
        _check("no failed gates", not failed, failures, str([g.get("name") for g in failed]))
        _check(
            "no critical skipped gates",
            not critical_skipped,
            failures,
            str([g.get("name") for g in critical_skipped]),
        )

    if failures:
        print(f"\nFAIL - {len(failures)} artifact issue(s)")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("\nPASS - real artifact checks passed")


if __name__ == "__main__":
    main()
