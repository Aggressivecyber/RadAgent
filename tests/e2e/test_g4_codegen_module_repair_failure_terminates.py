"""E2E test — module repair failure terminates pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_core.g4_codegen.repair.module_repair_loop import repair_module
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult, ModuleGateResult
from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_repair
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
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


class TestG4CodegenModuleRepairFailureTerminates:
    """Verify that repair failure routes pipeline to skip the module."""

    def test_route_after_repair_failed_skips_module(self) -> None:
        """When repair status is 'failed', pipeline should skip to next module."""
        state: G4CodegenSubgraphState = {
            "module_repair_results": {
                "geometry": {"status": "failed", "attempts": 3},
            },
        }

        next_node = _route_after_repair("geometry")(state)
        assert next_node != "geometry_hard_gate"
        # Should route to next module or integration

    def test_route_after_repair_success_retries_gate(self) -> None:
        """When repair status is 'repaired', pipeline should re-run hard gate."""
        state: G4CodegenSubgraphState = {
            "module_repair_results": {
                "geometry": {"status": "repaired", "attempts": 1},
            },
        }

        next_node = _route_after_repair("geometry")(state)
        assert next_node == "geometry_hard_gate"

    @pytest.mark.asyncio
    async def test_repair_loop_terminates(self, workspace: Path) -> None:
        """Repair module should terminate after max attempts."""
        original = ModuleAgentResult(
            module_name="physics",
            status="failed",
            generated_files=[
                GeneratedModuleFile(
                    path="src/Physics.cc",
                    operation="create_or_replace",
                    new_content="#include\n// broken\n",
                    generated_by="physics_module_agent",
                    module_name="physics",
                    rationale="test",
                ),
            ],
            errors=["empty include"],
        )

        gate = ModuleGateResult(
            module_name="physics",
            gate_type="hard",
            status="fail",
            errors=["empty include"],
        )

        with patch(
            "agent_core.g4_codegen.repair.module_repair_loop.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw
            mock_gw.call.return_value = AsyncMock(
                error="API unavailable",
                content="",
                parsed_json=None,
            )

            result = await repair_module("physics", {}, original, gate)

        assert result.status == "failed"
        assert len(result.repair_attempts) == 3
