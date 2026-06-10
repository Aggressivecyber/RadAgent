"""Test interface_contracts reflects actual codegen-visible boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_core.g4_codegen.interface_contracts import build_interface_contracts
from agent_core.models.gateway import reset_model_gateway
from agent_core.workspace.paths import STAGE_CODEGEN


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

    def test_contains_current_boundary_sections(self, workspace: Path) -> None:
        """Output must contain current CAD/GDML and metadata sections."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_format_test",
        )

        assert "cad_gdml" in contracts
        assert "downstream_handoffs" in contracts
        assert "metadata" in contracts

    def test_cad_gdml_is_list(self, workspace: Path) -> None:
        """cad_gdml should be a list."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_cad_test",
        )

        assert isinstance(contracts["cad_gdml"], list)

    def test_no_external_files_does_not_create_placeholder_contract(self, workspace: Path) -> None:
        """No CAD/GDML input should produce no CAD/GDML contract."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_no_external_test",
        )

        assert contracts["cad_gdml"] == []

    def test_downstream_handoffs_are_not_speculative(self, workspace: Path) -> None:
        """TCAD/SPICE handoffs should not be invented without explicit IR support."""
        contracts = build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_downstream_test",
        )

        assert contracts["downstream_handoffs"] == []

    def test_persists_to_file(self, workspace: Path) -> None:
        """interface_contracts.json should be persisted to disk."""
        build_interface_contracts(
            {"model_ir_id": "test"},
            {"requires_external_files": []},
            "ic_persist_test",
        )

        from agent_core.workspace.io import get_job_dir

        contracts_path = get_job_dir("ic_persist_test") / STAGE_CODEGEN / "interface_contracts.json"
        assert contracts_path.exists()

        saved = json.loads(contracts_path.read_text())
        assert "cad_gdml" in saved
        assert "downstream_handoffs" in saved
        assert "metadata" in saved

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
