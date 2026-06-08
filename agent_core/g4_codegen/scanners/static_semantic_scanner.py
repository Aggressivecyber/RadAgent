"""Static semantic scanner — checks generated code for forbidden patterns.

P0-6/P0-7: Severe issues (abstract instantiation, CAD claims, fake outputs,
G4Box fallback) are errors that cause scan failure, not just warnings.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── Error patterns (always fail the scan) ──────────────────────────
# P0-7: These are severe issues that must cause status=fail.
ERROR_PATTERNS: list[tuple[str, str]] = [
    # Empty include (broken C++)
    ("empty_include", r"^\s*#include\s*$"),
    ("include_whitespace_only", r"^\s*#include\s+\s*$"),
    # Abstract base class instantiation (compilation error)
    ("abstract_sensitive_detector", r"new\s+G4VSensitiveDetector"),
    ("abstract_hit", r"new\s+G4VHit"),
    ("abstract_detector_construction", r"new\s+G4VUserDetectorConstruction"),
    ("abstract_primary_generator", r"new\s+G4VUserPrimaryGeneratorAction"),
    ("abstract_action_initialization", r"new\s+G4VUserActionInitialization"),
    # Untyped std::map (compilation error)
    ("untyped_registry_map", r"std::map\s+registry_"),
    ("untyped_detectors_map", r"std::map\s+detectors_"),
    # CAD/GDML fake conversion claims
    ("freecad_reference", r"FreeCAD"),
    ("cadmesh_reference", r"cadmesh|CADMesh"),
    ("step_conversion_claim", r"STEP.*convert|convert.*STEP"),
    ("stl_conversion_claim", r"STL.*convert|convert.*STL"),
    ("ply_conversion_claim", r"PLY.*convert|convert.*PLY"),
    # G4Box fallback (not real geometry)
    ("g4box_fallback", r"G4Box\s*\(\s*\"fallback|fallback.*G4Box"),
    # Fake TCAD/SPICE output
    ("fake_tcad_output", r"fake.*TCAD|TCAD.*fake|dummy.*TCAD"),
    ("fake_spice_output", r"fake.*SPICE|SPICE.*fake|dummy.*SPICE"),
    # Content field (must use new_content)
    ("content_field_used", r"\"content\"\s*:"),
    # Markdown fence (LLM artifact)
    ("markdown_fence", r"```"),
]

# ── Warning patterns (logged but do not fail the scan) ─────────────
WARNING_PATTERNS: list[tuple[str, str]] = [
    ("todo_marker", r"TODO"),
    ("not_implemented", r"NotImplemented"),
    ("stub_marker", r"\bstub\b"),
    ("dummy_marker", r"\bdummy\b"),
    ("placeholder_marker", r"PLACEHOLDER|\{\{|\}\}"),
    ("untyped_std_map", r"std::map\s+\w+\s*;"),
]

_REGEX_FLAGS = re.IGNORECASE | re.MULTILINE


def scan_generated_code(
    proposed_patch: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Scan all generated code for forbidden patterns.

    P0-6: Severe issues cause status=fail (not just warning).
    P0-7: Includes abstract instantiation, CAD claims, fake outputs,
    G4Box fallback, content field usage.
    """
    findings: list[dict[str, Any]] = []
    all_passed = True

    for f in proposed_patch.get("changed_files", []):
        path = f.get("path", "")
        content = f.get("new_content", "")

        # Check for 'content' field (must use 'new_content')
        if "content" in f:
            findings.append(
                {
                    "file": path,
                    "issue": "content_field_present",
                    "severity": "error",
                    "message": (
                        "File contains deprecated 'content' field; only 'new_content' is allowed"
                    ),
                }
            )
            all_passed = False

        if not content:
            findings.append(
                {
                    "file": path,
                    "issue": "empty_content",
                    "severity": "error",
                    "message": "new_content is empty",
                }
            )
            all_passed = False
            continue

        # Scan error patterns (always fail)
        for issue_name, pattern in ERROR_PATTERNS:
            if re.search(pattern, content, _REGEX_FLAGS):
                findings.append(
                    {
                        "file": path,
                        "issue": issue_name,
                        "severity": "error",
                        "message": f"Found forbidden pattern: {issue_name}",
                    }
                )
                all_passed = False

        # Scan warning patterns (log but don't fail)
        for issue_name, pattern in WARNING_PATTERNS:
            if re.search(pattern, content, _REGEX_FLAGS):
                findings.append(
                    {
                        "file": path,
                        "issue": issue_name,
                        "severity": "warning",
                        "message": f"Found warning pattern: {issue_name}",
                    }
                )

    result = {
        "status": "pass" if all_passed else "fail",
        "total_files": len(proposed_patch.get("changed_files", [])),
        "findings": findings,
        "error_count": sum(1 for f in findings if f["severity"] == "error"),
        "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
    }

    # Persist
    from agent_core.config.workspace import get_job_dir

    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    scan_path = codegen_dir / "static_semantic_scan.json"
    scan_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    return result
