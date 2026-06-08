"""Cross-file hard gate — validates consistency across all generated files.

P0-1 to P0-5: Uses relative paths (no 08_geant4/ prefix).
Checks CMakeLists.txt, main.cc, source inclusion, core module completeness.
"""

from __future__ import annotations

import json
from typing import Any

# P0-5: 10 core modules that must each have at least one file
REQUIRED_MODULES = [
    "material",
    "geometry",
    "placement",
    "source",
    "physics",
    "sensitive_detector",
    "scoring",
    "output_manager",
    "action_initialization",
    "main_cmake",
]


def run_cross_file_hard_gate(
    proposed_patch: dict[str, Any],
    code_architecture_plan: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Run cross-file hard gate checks.

    P0-1: All paths are relative to 08_geant4 (no prefix).
    P0-2: Checks CMakeLists.txt exists.
    P0-3: Checks main.cc exists.
    P0-4: Checks CMakeLists.txt includes all src/*.cc.
    P0-5: Checks 10 core modules each have at least one file.
    """
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    all_passed = True

    files = proposed_patch.get("changed_files", [])
    file_paths = {f["path"] for f in files}
    file_contents = {f["path"]: f.get("new_content", "") for f in files}

    # ── Per-file checks ──────────────────────────────────────────────
    for f in files:
        path = f.get("path", "")

        # P0-8: Reject any 'content' field (even with new_content)
        if "content" in f:
            checks.append(
                {
                    "check": "no_content_field",
                    "file": path,
                    "status": "fail",
                    "message": (
                        "File uses deprecated 'content' field; only 'new_content' is allowed"
                    ),
                }
            )
            all_passed = False
            errors.append(f"{path}: uses 'content' field")

        # Check non-empty new_content
        if not f.get("new_content", "").strip():
            checks.append(
                {
                    "check": "non_empty_new_content",
                    "file": path,
                    "status": "fail",
                    "message": "new_content is empty",
                }
            )
            all_passed = False

        # Check required per-file fields
        for required_field in ("path", "new_content", "zone", "generated_by", "module_name"):
            if not f.get(required_field):
                checks.append(
                    {
                        "check": f"file_has_{required_field}",
                        "file": path,
                        "status": "fail",
                        "message": f"Missing required field: {required_field}",
                    }
                )
                all_passed = False

    # ── P0-2: CMakeLists.txt must exist ──────────────────────────────
    has_cmake = "CMakeLists.txt" in file_paths
    checks.append(
        {
            "check": "cmake_exists",
            "status": "pass" if has_cmake else "fail",
            "message": ("CMakeLists.txt is present" if has_cmake else "CMakeLists.txt is required"),
        }
    )
    if not has_cmake:
        all_passed = False
        errors.append("CMakeLists.txt is missing from proposed_patch")

    # ── P0-3: main.cc must exist ─────────────────────────────────────
    has_main = "main.cc" in file_paths
    checks.append(
        {
            "check": "main_cc_exists",
            "status": "pass" if has_main else "fail",
            "message": ("main.cc is present" if has_main else "main.cc is required"),
        }
    )
    if not has_main:
        all_passed = False
        errors.append("main.cc is missing from proposed_patch")

    # ── P0-4: CMakeLists.txt must include all src/*.cc ───────────────
    # P0-1: Use relative paths (no 08_geant4/ prefix)
    cmake_content = file_contents.get("CMakeLists.txt", "")
    src_files = sorted(p for p in file_paths if p.startswith("src/") and p.endswith(".cc"))
    if cmake_content and src_files:
        for src in src_files:
            src_name = src.split("/")[-1]
            # Check if CMake references the source file
            if src_name not in cmake_content and src not in cmake_content:
                checks.append(
                    {
                        "check": "cmake_includes_source",
                        "file": src,
                        "status": "fail",
                        "message": (f"CMakeLists.txt does not include {src_name}"),
                    }
                )
                all_passed = False
                errors.append(f"CMakeLists.txt does not include {src_name}")

    # ── P0-5: Core module completeness ───────────────────────────────
    modules_in_patch = {f.get("module_name", "") for f in files}
    for module in REQUIRED_MODULES:
        present = module in modules_in_patch
        checks.append(
            {
                "check": "required_module_present",
                "module_name": module,
                "status": "pass" if present else "fail",
                "message": (
                    f"Module '{module}' has generated files"
                    if present
                    else f"Required module '{module}' has no generated files"
                ),
            }
        )
        if not present:
            all_passed = False
            errors.append(f"Required module '{module}' has no generated files")

    # ── Header/source pair check ─────────────────────────────────────
    headers = {p for p in file_paths if p.endswith(".hh") or p.endswith(".hpp") or p.endswith(".h")}
    sources = {p for p in file_paths if p.endswith(".cc") or p.endswith(".cpp")}
    for src in sources:
        expected_header = (
            src.replace("/src/", "/include/").replace(".cc", ".hh").replace(".cpp", ".h")
        )
        if expected_header in headers:
            header_name = expected_header.split("/")[-1]
            src_content = file_contents.get(src, "")
            if header_name not in src_content:
                checks.append(
                    {
                        "check": "source_includes_header",
                        "file": src,
                        "status": "warn",
                        "message": f"Source may not include {header_name}",
                    }
                )

    # ── No duplicate main ────────────────────────────────────────────
    main_count = sum(1 for p, c in file_contents.items() if "int main(" in c and p.endswith(".cc"))
    checks.append(
        {
            "check": "no_duplicate_main",
            "status": "pass" if main_count <= 1 else "fail",
            "message": f"Found {main_count} main() definitions",
        }
    )
    if main_count > 1:
        all_passed = False

    result = {
        "status": "pass" if all_passed else "fail",
        "checks": checks,
        "errors": errors,
    }

    # Persist
    from agent_core.config.workspace import get_job_dir

    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    gate_path = codegen_dir / "cross_file_hard_gate.json"
    gate_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    return result
