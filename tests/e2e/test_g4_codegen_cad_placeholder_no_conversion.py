"""E2E test — CAD/GDML placeholder does not perform real conversion."""

# noqa: E501
from __future__ import annotations

# noqa: E501
from pathlib import Path

import pytest
from agent_core.g4_codegen.interface_contracts import build_interface_contracts
from agent_core.models.gateway import reset_model_gateway


@pytest.fixture(autouse=True)
def _reset_gw() -> None:
    reset_model_gateway()
    yield
    reset_model_gateway()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestG4CodegenCadPlaceholderNoConversion:
    """Verify CAD/GDML interface contracts do not perform real conversion."""

    def test_no_cad_conversion(self, workspace: Path) -> None:
        """CAD/GDML should produce placeholder, not real conversion."""
        g4_model_ir = {
            "model_ir_id": "cad_test",
            "components": [
                {
                    "component_id": "complex_shape",
                    "geometry_type": "cad_import",
                    "source_file": "complex_shape.step",
                },
            ],
        }

        geometry_strategy = {
            "requires_external_files": [
                {
                    "component_id": "complex_shape",
                    "path": "complex_shape.step",
                    "source_type": "STEP",
                },
            ],
        }

        contracts = build_interface_contracts(g4_model_ir, geometry_strategy, "cad_test")

        cad = contracts["cad_gdml"]
        assert len(cad) > 0

        # Should have conversion_required=True but status=not_implemented
        cad_contract = cad[0]
        assert cad_contract["conversion_required"] is True
        assert cad_contract["conversion_status"] == "not_implemented"
        assert "clarification" in cad_contract["action"] or "future" in cad_contract["action"]

    def test_no_cad_file_produces_placeholder(self, workspace: Path) -> None:
        """Without CAD files, should produce a 'no CAD' placeholder."""
        g4_model_ir = {"model_ir_id": "no_cad_test"}
        geometry_strategy = {"requires_external_files": []}

        contracts = build_interface_contracts(g4_model_ir, geometry_strategy, "no_cad_test")

        cad = contracts["cad_gdml"]
        assert len(cad) > 0
        assert cad[0]["conversion_required"] is False

    def test_no_freecad_or_cadmesh_in_scan(self, workspace: Path) -> None:
        """Static scanner should detect fake CAD conversion claims."""
        from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code

        patch_with_cad = {
            "changed_files": [
                {
                    "path": "src/Geometry.cc",
                    "new_content": '#include "G4Box.hh"\n// FreeCAD conversion of STEP file\nauto* solid = new G4Box("box", 1*m, 1*m, 1*m);\n',  # noqa: E501
                },
            ],
        }

        scan = scan_generated_code(patch_with_cad, "cad_scan_test")

        # Should detect FreeCAD reference
        freecad_findings = [
            f
            for f in scan["findings"]
            if f["issue"] in ("freecad_reference", "step_conversion_claim")
        ]
        assert len(freecad_findings) > 0, (
            "Static scan should detect FreeCAD/STEP conversion references"
        )
