"""Test that module repair stops after MAX_REPAIR_ATTEMPTS."""

from __future__ import annotations

from pathlib import Path
from typing import Any
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
            f"Repair failed after {MAX_REPAIR_ATTEMPTS} attempts" in e
            for e in result.errors
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
