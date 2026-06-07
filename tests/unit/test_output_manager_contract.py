"""Tests for OutputManager contract — verifies g4_output_package compliance."""

from __future__ import annotations

from typing import Any



def _minimal_model_ir_for_output() -> dict[str, Any]:
    """Return a minimal model IR with scoring for OutputManager tests."""
    return {
        "model_ir_id": "test_output",
        "job_id": "test_output",
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
            {
                "scoring_id": "event_table",
                "scoring_type": "region",
                "quantities": ["event_id", "edep_MeV", "x_mm", "y_mm", "z_mm"],
                "target_component_id": "sensitive",
                "output_format": "csv",
                "source_evidence": ["user_spec"],
            },
        ],
        "ledger": {"entries": [], "version": "1.0"},
    }


class TestOutputManagerContract:
    """Verify OutputManager codegen produces g4_output_package compliant output."""

    async def test_generates_output_manager_module(self) -> None:
        """OutputManager codegen must produce a module entry."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_for_output()}
        result = await output_manager_codegen(state)

        modules = result.get("code_modules", [])
        assert len(modules) == 1
        mod = modules[0]
        assert mod["module_name"] == "OutputManager"
        assert "OutputManager.cc" in mod["source_files"]
        assert "OutputManager.hh" in mod["header_files"]

    async def test_header_contains_required_methods(self) -> None:
        """OutputManager.hh must declare all g4_output_package methods."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_for_output()}
        result = await output_manager_codegen(state)

        content = result["code_modules"][0]["generated_content"]
        header = content["OutputManager::OutputManager.hh"]

        # Required method declarations
        assert "WriteG4Summary" in header
        assert "WriteProvenance" in header
        assert "WriteRunLog" in header
        assert "SetOutputDir" in header
        assert "SetModelIRId" in header
        assert "SetJobId" in header
        assert "SetPhysicsList" in header

    async def test_source_generates_g4_summary_json(self) -> None:
        """OutputManager.cc must generate g4_summary.json."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_for_output()}
        result = await output_manager_codegen(state)

        content = result["code_modules"][0]["generated_content"]
        source = content["OutputManager::OutputManager.cc"]

        assert "g4_summary.json" in source
        assert "n_events" in source
        assert "physics_list" in source
        assert "timestamp" in source

    async def test_source_generates_provenance_json(self) -> None:
        """OutputManager.cc must generate provenance.json."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_for_output()}
        result = await output_manager_codegen(state)

        content = result["code_modules"][0]["generated_content"]
        source = content["OutputManager::OutputManager.cc"]

        assert "provenance.json" in source
        assert "model_ir_id" in source
        assert "geant4_version" in source

    async def test_source_generates_run_log(self) -> None:
        """OutputManager.cc must generate run_log.txt."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_for_output()}
        result = await output_manager_codegen(state)

        content = result["code_modules"][0]["generated_content"]
        source = content["OutputManager::OutputManager.cc"]

        assert "run_log.txt" in source

    async def test_scoring_outputs_derived_from_model_ir(self) -> None:
        """OutputManager must write CSV files based on scoring specs, not invented."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_for_output()}
        result = await output_manager_codegen(state)

        content = result["code_modules"][0]["generated_content"]
        source = content["OutputManager::OutputManager.cc"]

        # Must reference scoring IDs from model IR
        assert "edep_sensitive" in source
        assert "dose_3d" in source
        assert "event_table" in source
        # Must reference target component
        assert "sensitive" in source

    async def test_no_empty_scoring_skips_module(self) -> None:
        """Model IR without scoring should produce no OutputManager module."""
        from agent_core.g4_modeling.codegen.output_manager_codegen import (
            output_manager_codegen,
        )

        model_ir = _minimal_model_ir_for_output()
        del model_ir["scoring"]
        result = await output_manager_codegen({"g4_model_ir": model_ir})
        assert result.get("code_modules", []) == []
