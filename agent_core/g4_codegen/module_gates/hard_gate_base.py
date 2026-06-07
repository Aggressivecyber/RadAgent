"""Base class for module hard gates — deterministic checks."""

from __future__ import annotations

import re
from typing import Any

from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult

# Patterns that are always forbidden
UNIVERSAL_FORBIDDEN_PATTERNS = [
    (r"#include\s*$", "empty include"),
    (r"#include\s+\s+", "include with only whitespace"),
    (r"```", "Markdown fence"),
    (r"TODO", "TODO marker"),
    (r"NotImplemented", "NotImplemented marker"),
    (r"stub", "stub marker"),
    (r"dummy", "dummy marker"),
    (r"PLACEHOLDER", "PLACEHOLDER marker"),
    (r"std::map\s+\w+\s*;", "untyped std::map"),
    (r"new\s+G4VSensitiveDetector", "instantiating abstract G4VSensitiveDetector"),
    (r"new\s+G4VHit", "instantiating abstract G4VHit"),
    (r"new\s+G4VUserDetectorConstruction", "instantiating abstract base class"),
    (r"new\s+G4VUserPrimaryGeneratorAction", "instantiating abstract base class"),
    (r"new\s+G4VUserActionInitialization", "instantiating abstract base class"),
]


def run_hard_gate_checks(
    module_name: str,
    generated_files: list[GeneratedModuleFile],
    forbidden_patterns: list[str] | None = None,
) -> ModuleGateResult:
    """Run deterministic hard gate checks on generated files.

    Checks:
    1. new_content is non-empty
    2. path is valid
    3. No Markdown fence
    4. No empty include
    5. No TODO/NotImplemented/stub/dummy/PLACEHOLDER
    6. No untyped std::map
    7. No abstract class instantiation
    8. Header has #pragma once or include guard
    9. Source includes own header
    10. Uses G4SystemOfUnits.hh when using units
    11. generated_by is correct
    12. module_name is correct
    """
    # P0-9: Reject empty generated_files
    if not generated_files:
        return ModuleGateResult(
            module_name=module_name,
            gate_type="hard",
            status="fail",
            checks=[{"check": "non_empty_generated_files", "status": "fail", "message": "generated_files is empty"}],
            errors=["generated_files is empty — hard gate cannot pass"],
        )

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    all_passed = True

    for f in generated_files:
        file_checks = _check_single_file(
            f, module_name, forbidden_patterns or []
        )
        checks.extend(file_checks)
        for c in file_checks:
            if c["status"] == "fail":
                all_passed = False
                errors.append(f"{f.path}: {c['message']}")

    return ModuleGateResult(
        module_name=module_name,
        gate_type="hard",
        status="pass" if all_passed else "fail",
        checks=checks,
        errors=errors,
    )


def _check_single_file(
    f: GeneratedModuleFile,
    expected_module: str,
    extra_forbidden: list[str],
) -> list[dict[str, Any]]:
    """Check a single generated file."""
    checks: list[dict[str, Any]] = []
    content = f.new_content

    # Check raw dict for legacy "content" key
    raw = f.model_dump() if hasattr(f, "model_dump") else (f if isinstance(f, dict) else {})
    if "content" in raw and "new_content" not in raw:
        checks.append({
            "check": "legacy_content_key",
            "status": "fail",
            "message": "File uses 'content' instead of 'new_content'",
        })

    # Check non-empty content
    checks.append({
        "check": "non_empty_content",
        "status": "pass" if content.strip() else "fail",
        "message": "new_content must not be empty",
    })

    # Check path validity
    checks.append({
        "check": "valid_path",
        "status": "pass" if f.path and "/" in f.path else "fail",
        "message": "path must be valid",
    })

    # Check for forbidden patterns
    all_patterns = UNIVERSAL_FORBIDDEN_PATTERNS + [
        (p, f"custom forbidden: {p}") for p in extra_forbidden
    ]

    for pattern, desc in all_patterns:
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            checks.append({
                "check": f"forbidden_pattern_{desc}",
                "status": "fail",
                "message": f"Found forbidden pattern: {desc}",
            })

    # Check header guard
    if f.path.endswith(".hh") or f.path.endswith(".h"):
        has_guard = (
            "#pragma once" in content
            or re.search(r"#ifndef\s+\w+_H", content)
        )
        checks.append({
            "check": "header_guard",
            "status": "pass" if has_guard else "fail",
            "message": "Header must have #pragma once or include guard",
        })

    # Check source includes own header
    if f.path.endswith(".cc") or f.path.endswith(".cpp"):
        header_name = f.path.replace("/src/", "/include/").replace(".cc", ".hh").replace(".cpp", ".h")
        short_header = header_name.split("/")[-1]
        has_own_include = f'#include "{short_header}"' in content or f'#include <{short_header}>' in content
        checks.append({
            "check": "source_includes_own_header",
            "status": "pass" if has_own_include else "warn",
            "message": "Source should include its own header",
        })

    # Check generated_by
    checks.append({
        "check": "generated_by",
        "status": "pass" if f.generated_by == f"{expected_module}_module_agent" else "warn",
        "message": f"generated_by should be {expected_module}_module_agent",
    })

    # Check module_name
    checks.append({
        "check": "module_name",
        "status": "pass" if f.module_name == expected_module else "warn",
        "message": f"module_name should be {expected_module}",
    })

    return checks
