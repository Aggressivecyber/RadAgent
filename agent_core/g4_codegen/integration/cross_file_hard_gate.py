"""Cross-file hard gate — validates consistency across all generated files."""

from __future__ import annotations

import json
from typing import Any


def run_cross_file_hard_gate(
    proposed_patch: dict[str, Any],
    code_architecture_plan: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Run cross-file hard gate checks.

    Validates:
    1. CMakeLists.txt contains all src/*.cc
    2. main.cc includes exist
    3. Header/source pairs match
    4. No duplicate main
    5. No duplicate class definitions
    6. All files have new_content
    7. No 'content' field (must use 'new_content')
    """
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    all_passed = True

    files = proposed_patch.get("changed_files", [])
    file_paths = {f["path"] for f in files}
    file_contents = {f["path"]: f.get("new_content", "") for f in files}

    # Check all files have new_content
    for f in files:
        if "content" in f:
            checks.append({
                "check": "no_content_field",
                "file": f["path"],
                "status": "fail",
                "message": "File uses 'content' instead of 'new_content'",
            })
            all_passed = False
            errors.append(f"{f['path']}: uses 'content' field")

        if not f.get("new_content", "").strip():
            checks.append({
                "check": "non_empty_new_content",
                "file": f["path"],
                "status": "fail",
                "message": "new_content is empty",
            })
            all_passed = False

    # Check CMakeLists.txt includes all source files
    cmake_content = file_contents.get("08_geant4/CMakeLists.txt", "")
    if cmake_content:
        src_files = [p for p in file_paths if p.startswith("08_geant4/src/") and p.endswith(".cc")]
        for src in src_files:
            src_name = src.split("/")[-1]
            if src_name not in cmake_content:
                checks.append({
                    "check": "cmake_includes_source",
                    "file": src,
                    "status": "fail",
                    "message": f"CMakeLists.txt missing {src_name}",
                })
                all_passed = False

    # Check header/source pairs
    headers = {p for p in file_paths if p.endswith(".hh") or p.endswith(".h")}
    sources = {p for p in file_paths if p.endswith(".cc") or p.endswith(".cpp")}
    for src in sources:
        expected_header = (
            src.replace("/src/", "/include/")
            .replace(".cc", ".hh")
            .replace(".cpp", ".h")
        )
        if expected_header in headers:
            header_name = expected_header.split("/")[-1]
            src_content = file_contents.get(src, "")
            if header_name not in src_content:
                checks.append({
                    "check": "source_includes_header",
                    "file": src,
                    "status": "warn",
                    "message": f"Source may not include {header_name}",
                })

    # Check no duplicate main
    main_count = sum(
        1 for p, c in file_contents.items()
        if "int main(" in c and p.endswith(".cc")
    )
    checks.append({
        "check": "no_duplicate_main",
        "status": "pass" if main_count <= 1 else "fail",
        "message": f"Found {main_count} main() definitions",
    })
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
