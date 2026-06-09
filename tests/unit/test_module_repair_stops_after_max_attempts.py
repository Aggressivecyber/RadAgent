"""Test that module repair stops after MAX_REPAIR_ATTEMPTS."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.g4_codegen.repair.module_repair_loop import (
    MAX_REPAIR_ATTEMPTS,
    repair_module,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult, ModuleGateResult
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


def _make_original_result() -> ModuleAgentResult:
    return ModuleAgentResult(
        module_name="geometry",
        status="failed",
        generated_files=[
            GeneratedModuleFile(
                path="src/Detector.cc",
                operation="create_or_replace",
                new_content='#include "Detector.hh"\n// broken code\n#include\n',
                generated_by="geometry_module_agent",
                module_name="geometry",
                rationale="test",
            ),
        ],
        errors=["empty include"],
    )


def _make_gate_result() -> ModuleGateResult:
    return ModuleGateResult(
        module_name="geometry",
        gate_type="hard",
        status="fail",
        errors=["empty include"],
    )


class TestModuleRepairStopsAfterMaxAttempts:
    """Verify repair_module stops after MAX_REPAIR_ATTEMPTS."""

    @pytest.mark.asyncio
    async def test_stops_after_max_attempts(self, workspace: Path) -> None:
        """repair_module should stop after MAX_REPAIR_ATTEMPTS and return failed status."""
        original = _make_original_result()
        gate = _make_gate_result()
        context = {"module_name": "geometry"}

        # Mock gateway to always return a repair attempt that doesn't fix the issue
        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            # Gateway returns a repair attempt that still has issues
            mock_gw.call.return_value = AsyncMock(
                error=None,
                content='{"module_name": "geometry", "status": "repaired", '
                '"generated_files": [{"path": "src/Detector.cc", '
                '"new_content": "#include \\"Detector.hh\\"\\n// still broken\\n#include\\n", '
                '"generated_by": "geometry_module_agent", "module_name": "geometry", '
                '"rationale": "repaired"}], '
                '"errors": [], "warnings": []}',
                parsed_json={
                    "module_name": "geometry",
                    "status": "repaired",
                    "generated_files": [
                        {
                            "path": "src/Detector.cc",
                            "new_content": '#include "Detector.hh"\n// still broken\n#include\n',
                            "generated_by": "geometry_module_agent",
                            "module_name": "geometry",
                            "rationale": "repaired",
                        },
                    ],
                    "errors": [],
                    "warnings": [],
                },
            )

            result = await repair_module("geometry", context, original, gate)

        # Should have stopped after MAX_REPAIR_ATTEMPTS
        assert result.status == "failed"
        assert len(result.repair_attempts) == MAX_REPAIR_ATTEMPTS
        assert any(
            f"Repair failed after {MAX_REPAIR_ATTEMPTS} attempts" in e for e in result.errors
        )

    @pytest.mark.asyncio
    async def test_max_attempts_is_three(self) -> None:
        """MAX_REPAIR_ATTEMPTS should be 3."""
        assert MAX_REPAIR_ATTEMPTS == 3

    @pytest.mark.asyncio
    async def test_gateway_called_max_attempts_times(self, workspace: Path) -> None:
        """Gateway should be called exactly MAX_REPAIR_ATTEMPTS times."""
        original = _make_original_result()
        gate = _make_gate_result()
        context = {"module_name": "geometry"}

        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_gw.call.return_value = AsyncMock(
                error="API error",
                content="",
                parsed_json=None,
            )

            await repair_module("geometry", context, original, gate)

        assert mock_gw.call.call_count == MAX_REPAIR_ATTEMPTS

    @pytest.mark.asyncio
    async def test_normalizes_repair_files_content_shape(self, workspace: Path) -> None:
        """Repair responses using files/content should normalize to generated files."""
        original = _make_original_result()
        gate = _make_gate_result()
        context = {"module_name": "geometry"}

        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw
            mock_gw.call.return_value = AsyncMock(
                error=None,
                content="{}",
                parsed_json={
                    "module_name": "geometry",
                    "status": "repaired",
                    "files": [
                        {
                            "path": "src/Detector.cc",
                            "content": '#include "Detector.hh"\nvoid build() {}\n',
                            "generated_by": "geometry_module_agent",
                            "module_name": "geometry",
                            "rationale": "repaired",
                        }
                    ],
                    "errors": [],
                    "warnings": [],
                },
            )

            result = await repair_module("geometry", context, original, gate)

        assert result.status == "repaired"
        assert result.generated_files[0].new_content == '#include "Detector.hh"\nvoid build() {}\n'
        assert "content" not in result.generated_files[0].model_dump()

    @pytest.mark.asyncio
    async def test_partial_repair_preserves_unmodified_files(self, workspace: Path) -> None:
        """Repair responses may return only changed files, but module output stays complete."""
        original = ModuleAgentResult(
            module_name="geometry",
            status="failed",
            generated_files=[
                GeneratedModuleFile(
                    path="include/Detector.hh",
                    operation="create_or_replace",
                    new_content=(
                        "#ifndef DETECTOR_HH\n#define DETECTOR_HH\n"
                        "class Detector {};\n#endif\n"
                    ),
                    generated_by="geometry_module_agent",
                    module_name="geometry",
                    rationale="test",
                ),
                GeneratedModuleFile(
                    path="src/Detector.cc",
                    operation="create_or_replace",
                    new_content='#include "Detector.hh"\n#include\n',
                    generated_by="geometry_module_agent",
                    module_name="geometry",
                    rationale="test",
                ),
            ],
            errors=["empty include"],
        )
        gate = _make_gate_result()
        context = {"module_name": "geometry"}

        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw
            mock_gw.call.return_value = AsyncMock(
                error=None,
                content="{}",
                parsed_json={
                    "module_name": "geometry",
                    "status": "repaired",
                    "generated_files": [
                        {
                            "path": "src/Detector.cc",
                            "new_content": '#include "Detector.hh"\nvoid DetectorBuild() {}\n',
                            "generated_by": "geometry_module_agent",
                            "module_name": "geometry",
                            "rationale": "repaired",
                        }
                    ],
                },
            )

            result = await repair_module("geometry", context, original, gate)

        assert result.status == "repaired"
        assert {f.path for f in result.generated_files} == {
            "include/Detector.hh",
            "src/Detector.cc",
        }
        assert len(result.repair_attempts) == 1

    @pytest.mark.asyncio
    async def test_repair_uses_module_specific_hard_gate(self, workspace: Path) -> None:
        original = ModuleAgentResult(
            module_name="scoring",
            status="failed",
            generated_files=[
                GeneratedModuleFile(
                    path="include/ScoringManager.hh",
                    operation="create_or_replace",
                    new_content=(
                        "#ifndef SCORINGMANAGER_HH\n#define SCORINGMANAGER_HH\n"
                        "class ScoringManager {};\n#endif\n"
                    ),
                    generated_by="scoring_module_agent",
                    module_name="scoring",
                    rationale="test",
                ),
                GeneratedModuleFile(
                    path="src/ScoringManager.cc",
                    operation="create_or_replace",
                    new_content='#include "ScoringManager.hh"\n',
                    generated_by="scoring_module_agent",
                    module_name="scoring",
                    rationale="test",
                ),
            ],
            errors=["needs repair"],
        )
        gate = ModuleGateResult(
            module_name="scoring",
            gate_type="hard",
            status="fail",
            errors=["needs repair"],
        )
        context = {"module_name": "scoring"}

        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw
            mock_gw.call.return_value = AsyncMock(
                error=None,
                content="{}",
                parsed_json={
                    "module_name": "scoring",
                    "status": "repaired",
                    "generated_files": [
                        {
                            "path": "src/ScoringManager.cc",
                            "new_content": (
                                '#include "ScoringManager.hh"\n'
                                '#include "OutputManager.hh"\n'
                                "void RecordScoring() { "
                                "OutputManager::Instance()->WriteEvent(nullptr); }\n"
                            ),
                            "generated_by": "scoring_module_agent",
                            "module_name": "scoring",
                            "rationale": "repaired",
                        }
                    ],
                    "errors": [],
                    "warnings": [],
                },
            )

            result = await repair_module("scoring", context, original, gate, max_attempts=1)

        assert result.status == "failed"
        assert result.repair_attempts[0]["gate_status"] == "fail"

    @pytest.mark.asyncio
    async def test_repair_prunes_files_outside_module_contract(self, workspace: Path) -> None:
        original = ModuleAgentResult(
            module_name="placement",
            status="failed",
            generated_files=[
                GeneratedModuleFile(
                    path="include/PlacementManager.hh",
                    operation="create_or_replace",
                    new_content="#pragma once\nclass PlacementManager {};\n",
                    generated_by="placement_module_agent",
                    module_name="placement",
                    rationale="test",
                ),
                GeneratedModuleFile(
                    path="src/main.cc",
                    operation="create_or_replace",
                    new_content="",
                    generated_by="placement_module_agent",
                    module_name="placement",
                    rationale="out of scope",
                ),
            ],
            errors=["out of scope file"],
        )
        gate = ModuleGateResult(
            module_name="placement",
            gate_type="hard",
            status="fail",
            errors=["src/main.cc: new_content must not be empty"],
        )
        context = {
            "module_name": "placement",
            "module_contract": {
                "output_files": [
                    "include/PlacementManager.hh",
                    "src/PlacementManager.cc",
                ]
            },
        }

        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw
            mock_gw.call.return_value = AsyncMock(
                error=None,
                content="{}",
                parsed_json={
                    "module_name": "placement",
                    "status": "repaired",
                    "generated_files": [
                        {
                            "path": "include/PlacementManager.hh",
                            "new_content": (
                                "#pragma once\n"
                                "#include \"G4ThreeVector.hh\"\n"
                                "#include \"G4RotationMatrix.hh\"\n"
                                "class G4LogicalVolume;\n"
                                "class G4PVPlacement;\n"
                                "class PlacementManager {\n"
                                "public:\n"
                                "  G4PVPlacement* PlaceVolume(G4LogicalVolume*, const char*, "
                                "G4LogicalVolume*, const G4ThreeVector&, G4RotationMatrix*, "
                                "int, bool);\n"
                                "};\n"
                            ),
                            "generated_by": "placement_module_agent",
                            "module_name": "placement",
                            "rationale": "contract output",
                        },
                        {
                            "path": "src/PlacementManager.cc",
                            "new_content": (
                                "#include \"PlacementManager.hh\"\n"
                                "#include \"G4LogicalVolume.hh\"\n"
                                "#include \"G4PVPlacement.hh\"\n"
                                "G4PVPlacement* PlacementManager::PlaceVolume("
                                "G4LogicalVolume* logical, const char* name, "
                                "G4LogicalVolume* mother, const G4ThreeVector& position, "
                                "G4RotationMatrix* rotation, int copyNo, bool checkOverlaps) {\n"
                                "  return new G4PVPlacement(rotation, position, logical, name, "
                                "mother, false, copyNo, checkOverlaps);\n"
                                "}\n"
                            ),
                            "generated_by": "placement_module_agent",
                            "module_name": "placement",
                            "rationale": "contract output",
                        },
                    ],
                    "errors": [],
                    "warnings": [],
                },
            )

            result = await repair_module("placement", context, original, gate, max_attempts=1)

        assert result.status == "repaired"
        assert {f.path for f in result.generated_files} == {
            "include/PlacementManager.hh",
            "src/PlacementManager.cc",
        }
