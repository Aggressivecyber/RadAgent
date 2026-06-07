"""CMake Structure Validator — validates generated CMakeLists.txt.

Ensures the CMake file:
1. Has minimum required version
2. Has project() declaration
3. Finds Geant4 package
4. Links Geant4 libraries
5. Has correct source file globs
6. Has no hardcoded paths
"""

from __future__ import annotations

import re
from typing import Any


def validate_cmake_structure(cmake_content: str) -> tuple[bool, list[str]]:
    """Validate a CMakeLists.txt for Geant4 project structure.

    Returns (is_valid, list_of_issues).
    """
    issues: list[str] = []

    if not cmake_content.strip():
        issues.append("CMakeLists.txt is empty")
        return False, issues

    # Rule 1: cmake_minimum_required
    if not re.search(r"cmake_minimum_required\s*\(", cmake_content):
        issues.append("Missing cmake_minimum_required()")

    # Rule 2: project() declaration
    if not re.search(r"project\s*\(\s*\w+", cmake_content):
        issues.append("Missing project() declaration")

    # Rule 3: find_package(Geant4)
    if not re.search(r"find_package\s*\(\s*Geant4", cmake_content):
        issues.append("Missing find_package(Geant4)")

    # Rule 4: link_libraries or target_link_libraries with Geant4
    if not re.search(r"Geant4_LIBRARIES|Geant4::", cmake_content):
        issues.append("Missing Geant4 library linking")

    # Rule 5: No hardcoded absolute paths
    hardcoded_paths = re.findall(r"/home/|/usr/local/|/opt/", cmake_content)
    if hardcoded_paths:
        issues.append(f"Hardcoded absolute paths found: {hardcoded_paths[:3]}")

    # Rule 6: Has executable target
    if not re.search(r"add_executable\s*\(", cmake_content):
        issues.append("Missing add_executable()")

    # Rule 7: Include directories
    if not re.search(r"target_include_directories\s*\(|include_directories\s*\(", cmake_content):
        issues.append("Missing include directories setup")

    is_valid = len(issues) == 0
    return is_valid, issues


def validate_cmake_from_modules(
    modules: list[dict[str, Any]], cmake_content: str
) -> tuple[bool, list[str]]:
    """Validate CMakeLists.txt consistency with generated modules.

    Checks that source files referenced in modules exist in CMake globs.
    """
    issues: list[str] = []

    # Extract source file paths from modules
    module_sources = set()
    for mod in modules:
        target = mod.get("target_file", "")
        if target and target.endswith(".cc"):
            module_sources.add(target)

    # Check if CMake uses GLOB for sources (common pattern)
    has_glob = bool(re.search(r"file\s*\(\s*GLOB", cmake_content))

    if has_glob and module_sources:
        # GLOB patterns should cover all module source files
        source_dirs = re.findall(r"src/\*\.cc", cmake_content)
        if not source_dirs:
            issues.append("CMake GLOB does not cover src/*.cc")

    is_valid = len(issues) == 0
    return is_valid, issues
