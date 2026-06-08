"""Test interface_contracts produces correct JSON format with all three sections."""

from __future__ import annotations

import json
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


class TestInterfaceContractsFormat:
    """Verify interface_contracts outputs correct JSON format."""

    def test_contains_all_three_sections(self, workspace: Path) -> None:
        """Output must contain cad_gdml, g4_to_tcad, tcad_to_spice sections."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_format_test",
        )

        assert "cad_gdml" in contracts
        assert "g4_to_tcad" in contracts
        assert "tcad_to_spice" in contracts

    def test_cad_gdml_is_list(self, workspace: Path) -> None:
        """cad_gdml should be a list."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_cad_test",
        )

        assert isinstance(contracts["cad_gdml"], list)

    def test_g4_to_tcad_is_list(self, workspace: Path) -> None:
        """g4_to_tcad should be a list."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_g4tcad_test",
        )

        assert isinstance(contracts["g4_to_tcad"], list)
        assert len(contracts["g4_to_tcad"]) > 0

    def test_tcad_to_spice_is_list(self, workspace: Path) -> None:
        """tcad_to_spice should be a list."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_tcadspice_test",
        )

        assert isinstance(contracts["tcad_to_spice"], list)
        assert len(contracts["tcad_to_spice"]) > 0

    def test_g4_to_tcad_has_required_fields(self, workspace: Path) -> None:
        """G4→TCAD contract should have required fields."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_fields_test",
        )

        g4_tcad = contracts["g4_to_tcad"][0]
        assert "contract_id" in g4_tcad
        assert "conversion_required" in g4_tcad
        assert "conversion_status" in g4_tcad

    def test_tcad_to_spice_has_required_fields(self, workspace: Path) -> None:
        """TCAD→SPICE contract should have required fields."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_spice_test",
        )

        tcad_spice = contracts["tcad_to_spice"][0]
        assert "contract_id" in tcad_spice
        assert "conversion_required" in tcad_spice
        assert "conversion_status" in tcad_spice

    def test_persists_to_file(self, workspace: Path) -> None:
        """interface_contracts.json should be persisted to disk."""
        build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_persist_test",
        )

        from agent_core.config.workspace import get_job_dir

        contracts_path = get_job_dir("ic_persist_test") / "06_codegen" / "interface_contracts.json"
        assert contracts_path.exists()

        saved = json.loads(contracts_path.read_text())
        assert "cad_gdml" in saved
        assert "g4_to_tcad" in saved
        assert "tcad_to_spice" in saved

    def test_with_cad_files(self, workspace: Path) -> None:
        """With CAD files, cad_gdml should reflect them."""
        geometry_strategy = {
            "requires_external_files": [
                {
                    "component_id": "shield_block",
                    "path": "shield.step",
                    "source_type": "STEP",
                },
            ],
        }

        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            geometry_strategy,
            "ic_cad_files_test",
        )

        cad = contracts["cad_gdml"]
        assert len(cad) > 0
        assert cad[0]["conversion_required"] is True
        assert cad[0]["source_type"] == "STEP"
