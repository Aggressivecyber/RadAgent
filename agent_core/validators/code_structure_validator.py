"""Code structure validator for generated simulation code (Geant4, SPICE, TCAD)."""

from __future__ import annotations

import os
import re
from pathlib import Path


class CodeStructureValidator:
    """Validates structural correctness of generated simulation projects and files."""

    # Minimum required Geant4 class names (substring match in source files)
    _G4_REQUIRED_CLASSES = (
        "DetectorConstruction",
        "PhysicsList",
        "PrimaryGeneratorAction",
        "SteppingAction",
    )

    def validate_geant4_project(self, project_dir: str) -> tuple[bool, list[str]]:
        """Check Geant4 project directory for required files and classes."""
        errors: list[str] = []
        root = Path(project_dir)

        cmake = root / "CMakeLists.txt"
        if not cmake.is_file():
            errors.append("Missing CMakeLists.txt")
        else:
            ok, cmake_errs = self.validate_geant4_cmakelists(cmake.read_text())
            errors.extend(cmake_errs)

        for subdir in ("src", "include"):
            if not (root / subdir).is_dir():
                errors.append(f"Missing {subdir}/ directory")

        if not list(root.glob("src/*.cc")):
            errors.append("No .cc files in src/")

        if not list(root.glob("include/*.hh")):
            errors.append("No .hh files in include/")

        all_source = " ".join(
            p.read_text(errors="replace") for p in root.glob("src/*.cc")
        )
        for cls in self._G4_REQUIRED_CLASSES:
            if cls not in all_source:
                errors.append(f"Missing required class: {cls}")

        return (len(errors) == 0, errors)

    def validate_geant4_cmakelists(self, content: str) -> tuple[bool, list[str]]:
        """Check CMakeLists.txt for essential Geant4 cmake directives."""
        errors: list[str] = []
        low = content.lower()

        if "cmake_minimum_required" not in low:
            errors.append("Missing cmake_minimum_required()")
        if not re.search(r"project\s*\(", low):
            errors.append("Missing project()")
        if "find_package(geant4" not in low:
            errors.append("Missing find_package(Geant4)")
        if not re.search(r"target_link_libraries", low):
            errors.append("Missing target_link_libraries()")
        if "cxx_standard" not in low and "c++17" not in low and "c++14" not in low:
            errors.append("Missing C++ standard setting (CXX_STANDARD or c++17)")

        return (len(errors) == 0, errors)

    def validate_spice_netlist(self, content: str) -> tuple[bool, list[str]]:
        """Basic SPICE netlist syntax validation."""
        errors: list[str] = []
        low = content.lower()

        if not re.search(r"\.end\b", low):
            errors.append("Missing .end statement")

        analysis = re.search(r"\.(tran|dc|ac)\b", low)
        if not analysis:
            errors.append("Missing analysis directive (.tran/.dc/.ac)")

        # Check that referenced nodes are consistent (basic pass)
        lines = content.strip().splitlines()
        component_nodes: set[str] = set()
        for line in lines:
            if re.match(r"^[a-z]", line, re.IGNORECASE) and not line.startswith("."):
                nodes = re.findall(r"\b\d+\b", line)
                component_nodes.update(nodes)

        return (len(errors) == 0, errors)

    def validate_tcad_command_file(self, content: str) -> tuple[bool, list[str]]:
        """Stub for MVP-1 -- basic structure check placeholder."""
        return (True, [])
