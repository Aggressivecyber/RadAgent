"""Static C++ quality checks for OutputManager generated code.

Verifies structural correctness without requiring a C++ compiler:
  - Include guards present and correct
  - Source includes own header first
  - No empty or malformed #include lines
  - No bare G4int (must use standard int)
  - No free functions (all methods qualified as OutputManager::)
  - PascalCase method naming enforced
  - No forbidden patterns (using namespace std, etc.)
"""

from __future__ import annotations

import re
from typing import Any


def _minimal_model_ir_for_output() -> dict[str, Any]:
    """Return a minimal model IR with scoring for OutputManager tests."""
    return {
        "model_ir_id": "test_static_cpp",
        "job_id": "test_static_cpp",
        "modeling_mode": "realistic",
        "target_system": "Test Detector",
        "simplification_policy": {
            "allow_simplification": False,
            "requires_user_approval": True,
            "approved_simplifications": [],
        },
        "components": [
            {
                "component_id": "world",
                "display_name": "World",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 1000, "dy": 1000, "dz": 1000},
                "material_id": "G4_AIR",
                "source_evidence": ["standard"],
            },
            {
                "component_id": "sensitive",
                "display_name": "Sensitive Region",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 50, "dy": 50, "dz": 5},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "source_evidence": ["user_spec"],
            },
        ],
        "materials": [
            {
                "material_id": "G4_AIR",
                "name": "G4_AIR",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.001214,
                "source_evidence": ["NIST"],
            },
        ],
        "sources": [
            {
                "source_id": "proton",
                "particle_type": "proton",
                "energy": {"value": 10.0, "unit": "MeV", "distribution": "mono"},
                "beam": {"position": [0, 0, 500], "direction": [0, 0, -1]},
                "generator_type": "gps",
                "source_evidence": ["user_spec"],
            },
        ],
        "physics": {
            "physics_list": "QGSP_BIC",
            "selection_reasoning": "Standard EM for proton detector simulation",
            "source_evidence": ["geant4_guide"],
        },
        "scoring": [
            {
                "scoring_id": "edep_sensitive",
                "scoring_type": "region",
                "quantities": ["edep_MeV", "n_entries"],
                "target_component_id": "sensitive",
                "output_format": "csv",
                "source_evidence": ["user_spec"],
            },
            {
                "scoring_id": "dose_3d",
                "scoring_type": "mesh",
                "quantities": ["dose_Gy", "edep_MeV"],
                "target_component_id": "sensitive",
                "output_format": "csv",
                "source_evidence": ["user_spec"],
            },
        ],
        "ledger": {"entries": [], "version": "1.0"},
    }


async def _get_generated_code() -> dict[str, str]:
    """Run codegen and return {filename: content}."""
    from agent_core.g4_modeling.codegen.output_manager_codegen import (
        output_manager_codegen,
    )

    state = {"g4_model_ir": _minimal_model_ir_for_output()}
    result = await output_manager_codegen(state)
    return result["code_modules"][0]["generated_content"]


class TestCppIncludeGuard:
    """Verify include guard is present and well-formed."""

    async def test_header_has_include_guard(self) -> None:
        code = await _get_generated_code()
        header = code["OutputManager::OutputManager.hh"]

        assert "#ifndef OUTPUT_MANAGER_HH" in header
        assert "#define OUTPUT_MANAGER_HH" in header
        assert "#endif" in header

    async def test_guard_endif_at_end(self) -> None:
        code = await _get_generated_code()
        header = code["OutputManager::OutputManager.hh"]

        # Last non-empty line should be #endif
        lines = [line.strip() for line in header.splitlines() if line.strip()]
        assert lines[-1] == "#endif"


class TestCppIncludeOrder:
    """Verify source includes its own header first."""

    async def test_source_includes_own_header_first(self) -> None:
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        include_lines = [
            line.strip() for line in source.splitlines() if line.strip().startswith("#include")
        ]
        assert len(include_lines) > 0, "No includes found in source"

        first_include = include_lines[0]
        assert '"OutputManager.hh"' in first_include, (
            f"Source must include own header first, got: {first_include}"
        )

    async def test_geant4_includes_before_stl(self) -> None:
        """Geant4 headers should appear before STL headers in source."""
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        lines = source.splitlines()
        g4_include_idx = None
        stl_include_idx = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("#include"):
                continue
            if stripped.startswith("#include <G4") or stripped.startswith('#include "G4'):
                if g4_include_idx is None:
                    g4_include_idx = i
            elif stripped.startswith("#include <") and not stripped.startswith("#include <G4"):
                if stl_include_idx is None:
                    stl_include_idx = i

        if g4_include_idx is not None and stl_include_idx is not None:
            assert g4_include_idx < stl_include_idx, (
                f"Geant4 include at line {g4_include_idx} must come before "
                f"STL include at line {stl_include_idx}"
            )

    async def test_no_empty_includes_anywhere(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#include"):
                    assert len(stripped) > len("#include"), f"Empty include in {fname}:{line_no}"
                    has_angle = "<" in stripped and ">" in stripped
                    has_quote = '"' in stripped
                    assert has_angle or has_quote, (
                        f"Malformed include in {fname}:{line_no}: {stripped}"
                    )


class TestCppNoForbiddenPatterns:
    """Verify forbidden C++ patterns are absent."""

    async def test_no_using_namespace_std(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            assert "using namespace std" not in content, (
                f"{fname}: forbidden 'using namespace std' found"
            )

    async def test_no_bare_g4int(self) -> None:
        """Must use standard int, not G4int."""
        code = await _get_generated_code()
        for fname, content in code.items():
            # G4int as a type declaration (not in string/comment)
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                # Match G4int as word boundary (not part of longer word)
                if re.search(r"\bG4int\b", stripped):
                    raise AssertionError(
                        f"{fname}:{line_no}: bare G4int found, use int: {stripped}"
                    )

    async def test_no_todo_fixme(self) -> None:
        """Generated code should not contain TODO/FIXME markers."""
        code = await _get_generated_code()
        for fname, content in code.items():
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip().upper()
                assert "TODO" not in stripped, f"{fname}:{line_no}: TODO found"
                assert "FIXME" not in stripped, f"{fname}:{line_no}: FIXME found"

    async def test_no_free_write_functions(self) -> None:
        """All Write methods must be qualified as OutputManager::WriteXxx."""
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        for line_no, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            # Match bare void Write*() without class qualifier
            if re.match(r"^void\s+Write\w+\s*\(", stripped):
                assert "OutputManager::" in stripped, (
                    f"Line {line_no}: Unqualified free function: {stripped}"
                )


class TestCppPascalCaseMethods:
    """Verify all scoring methods use PascalCase."""

    async def test_scoring_methods_pascal_case(self) -> None:
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        # EdepSensitive, Dose3d — derived from edep_sensitive, dose_3d
        assert "OutputManager::WriteEdepSensitive()" in source
        assert "OutputManager::WriteDose3d()" in source

    async def test_no_snake_case_write_methods(self) -> None:
        """Must not have old-style snake_case Write methods."""
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        # Old patterns that must NOT exist
        forbidden = [
            "OutputManager::Writeedep_sensitive",
            "OutputManager::Writedose_3d",
            "OutputManager::Writeevent_table",
        ]
        for pattern in forbidden:
            assert pattern not in source, f"Old snake_case method found: {pattern}"

    async def test_header_declarations_pascal_case(self) -> None:
        code = await _get_generated_code()
        header = code["OutputManager::OutputManager.hh"]

        assert "void WriteEdepSensitive();" in header
        assert "void WriteDose3d();" in header


class TestCppOutputFilenames:
    """Verify CSV output filenames match scoring specs."""

    async def test_csv_paths_use_scoring_id(self) -> None:
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        # Must produce files named after scoring IDs
        assert '"/edep_sensitive.csv"' in source
        assert '"/dose_3d.csv"' in source

    async def test_output_files_under_outputdir(self) -> None:
        """All output file paths must start with outputDir_."""
        code = await _get_generated_code()
        source = code["OutputManager::OutputManager.cc"]

        # Find all ofstream opens
        for line in source.splitlines():
            stripped = line.strip()
            if "std::ofstream f(" in stripped:
                assert "outputDir_" in stripped, f"ofstream must use outputDir_ prefix: {stripped}"
