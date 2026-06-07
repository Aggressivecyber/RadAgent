"""Static semantic scanner — checks generated code for forbidden patterns."""

from __future__ import annotations

import json
import re
from typing import Any

SCAN_PATTERNS = [
    (r"#include\s*$", "empty_include"),
    (r"#include\s+\s+", "include_whitespace_only"),
    (r"```", "markdown_fence"),
    (r"TODO", "todo_marker"),
    (r"NotImplemented", "not_implemented"),
    (r"dummy", "dummy_marker"),
    (r"stub", "stub_marker"),
    (r"PLACEHOLDER", "placeholder_marker"),
    (r"std::map\s+\w+\s*;", "untyped_std_map"),
    (r"std::map\s+registry_", "untyped_registry_map"),
    (r"std::map\s+detectors_", "untyped_detectors_map"),
    (r"new\s+G4VSensitiveDetector", "abstract_instantiation_sd"),
    (r"new\s+G4VHit", "abstract_instantiation_hit"),
    (r"G4Box\s*\(\s*\"fallback", "g4box_fallback"),
    (r"FreeCAD", "freecad_reference"),
    (r"cadmesh", "cadmesh_reference"),
    (r"STEP.*convert", "step_conversion_claim"),
]


def scan_generated_code(
    proposed_patch: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Scan all generated code for forbidden patterns.

    Checks:
    1. Empty includes
    2. Markdown fences
    3. TODO/NotImplemented/stub/dummy/PLACEHOLDER
    4. Untyped std::map
    5. Abstract class instantiation
    6. G4Box fallback markers
    7. Fake CAD conversion
    8. Missing new_content
    9. Presence of content field
    """
    findings: list[dict[str, Any]] = []
    all_passed = True

    for f in proposed_patch.get("changed_files", []):
        path = f.get("path", "")
        content = f.get("new_content", "")

        # Check for 'content' field (must use 'new_content')
        if "content" in f and "new_content" not in f:
            findings.append({
                "file": path,
                "issue": "missing_new_content",
                "severity": "error",
                "message": "File uses 'content' instead of 'new_content'",
            })
            all_passed = False

        if not content:
            findings.append({
                "file": path,
                "issue": "empty_content",
                "severity": "error",
                "message": "new_content is empty",
            })
            all_passed = False
            continue

        # Scan for patterns
        for pattern, issue_name in SCAN_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                findings.append({
                    "file": path,
                    "issue": issue_name,
                    "severity": "error" if issue_name in (
                        "empty_include", "untyped_std_map", "abstract_instantiation_sd",
                        "untyped_registry_map", "untyped_detectors_map",
                    ) else "warning",
                    "message": f"Found {issue_name}",
                })
                if issue_name in ("empty_include", "untyped_std_map", "abstract_instantiation_sd"):
                    all_passed = False

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
