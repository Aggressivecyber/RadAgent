"""Test that hard gate detects empty #include using MULTILINE mode."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile


class TestHardGateDetectsEmptyIncludeMultiline:
    """Verify hard gate catches empty #include in multi-line files."""

    def test_detects_empty_include_in_multiline_file(self) -> None:
        """Hard gate should detect #include$ (no file) in a multi-line file."""
        content = """#include "G4SystemOfUnits.hh"
#include
#include "DetectorConstruction.hh"

class MyDetector : public G4VUserDetectorConstruction {
public:
    G4VPhysicalVolume* Construct() override;
};
"""
        files = [
            GeneratedModuleFile(
                path="src/Detector.cc",
                operation="create_or_replace",
                new_content=content,
                generated_by="geometry_module_agent",
                module_name="geometry",
                rationale="test",
            ),
            GeneratedModuleFile(
                path="include/Detector.hh",
                operation="create_or_replace",
                new_content="#pragma once\n#include <G4VUserDetectorConstruction.hh>\n",
                generated_by="geometry_module_agent",
                module_name="geometry",
                rationale="test",
            ),
        ]

        result = run_hard_gate_checks("geometry", files)

        assert result.status == "fail"
        has_empty_include = any(
            "empty include" in c.get("message", "").lower()
            or "empty_include" in c.get("check", "").lower()
            for c in result.checks
        )
        assert has_empty_include, "Hard gate did not detect empty #include"

    def test_detects_include_whitespace_only(self) -> None:
        """Hard gate should detect #include with only whitespace after it."""
        content = '#include "G4SystemOfUnits.hh"\n#include \n#include "Test.hh"\n'
        files = [
            GeneratedModuleFile(
                path="src/Test.cc",
                operation="create_or_replace",
                new_content=content,
                generated_by="test_module_agent",
                module_name="test",
                rationale="test",
            ),
            GeneratedModuleFile(
                path="include/Test.hh",
                operation="create_or_replace",
                new_content="#pragma once\n",
                generated_by="test_module_agent",
                module_name="test",
                rationale="test",
            ),
        ]

        result = run_hard_gate_checks("test", files)

        assert result.status == "fail"
