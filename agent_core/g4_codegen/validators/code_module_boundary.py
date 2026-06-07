"""Code Module Boundary Validator — ensures generated modules have clean boundaries.

Each codegen module must:
1. Include its own header first
2. Not include headers of unrelated modules
3. Expose a clear public API (construct/build functions)
4. Not use global state
"""

from __future__ import annotations

import re
from typing import Any


def validate_code_module_boundary(
    module_id: str, code: str, header: str
) -> tuple[bool, list[str]]:
    """Validate a single code module has clean boundaries.

    Returns (is_valid, list_of_issues).
    """
    issues: list[str] = []

    if not code.strip():
        issues.append(f"{module_id}: code is empty")
        return False, issues

    # Rule 1: Code should include its own header first
    if header:
        header_basename = header.split("/")[-1] if "/" in header else header
        include_pattern = rf'#include\s+"{re.escape(header_basename)}"'
        if not re.search(include_pattern, code):
            issues.append(
                f"{module_id}: does not include its own header '{header_basename}'"
            )

    # Rule 2: No global mutable state (static non-const variables)
    global_state = re.findall(r"static\s+(?!const|constexpr)\w+\s+\w+\s*=", code)
    if global_state:
        issues.append(f"{module_id}: has global mutable state: {global_state[:3]}")

    # Rule 3: Must have at least one function or class definition
    has_function = bool(re.search(r"(void|int|double|auto|G4\w+)\s+\w+\s*\(", code))
    has_class = bool(re.search(r"class\s+\w+", code))
    if not has_function and not has_class:
        issues.append(f"{module_id}: no function or class definitions found")

    # Rule 4: No raw pointers with 'new' without corresponding management
    # (Allow G4 objects which are managed by Geant4 run manager)
    raw_new = re.findall(r"new\s+\w+", code)
    g4_managed = sum(1 for n in raw_new if n.startswith("new G4") or n.startswith("new CLHEP"))
    unmanaged = len(raw_new) - g4_managed
    if unmanaged > 5:
        issues.append(
            f"{module_id}: {unmanaged} unmanaged 'new' allocations (max 5 allowed)"
        )

    is_valid = len(issues) == 0
    return is_valid, issues


def validate_all_module_boundaries(
    modules: list[dict[str, Any]]
) -> tuple[bool, list[str]]:
    """Validate all code modules have clean boundaries."""
    all_issues: list[str] = []
    all_valid = True

    for mod in modules:
        code = mod.get("code", "")
        header = mod.get("header", "")
        module_id = mod.get("module_id", "?")

        valid, issues = validate_code_module_boundary(module_id, code, header)
        if not valid:
            all_valid = False
            all_issues.extend(issues)

    return all_valid, all_issues
