"""Test that persist_codegen_output marks status='failed' when runtime audit fails."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestPersistMarksFailedOnRuntimeAuditFail:
    """Verify persist_codegen_output sets status='failed' on runtime audit failure."""

    @pytest.mark.asyncio
    async def test_failed_status_on_runtime_audit_fail(self, workspace: Path) -> None:
        """When runtime execution audit fails, g4_codegen_status should be failed."""
        state = {
            "job_id": "test_runtime_audit_fail",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/Test.cc",
                        "new_content": "// test",
                        "module_name": "simulation_core",
                    },
                    {
                        "path": "src/Beam.cc",
                        "new_content": "// test",
                        "module_name": "beam_physics",
                    },
                    {
                        "path": "main.cc",
                        "new_content": "// test",
                        "module_name": "runtime_app",
                    },
                ],
            },
            "module_results": {
                "simulation_core": {"status": "generated"},
                "beam_physics": {"status": "generated"},
                "runtime_app": {"status": "generated"},
            },
            "global_integration_agent_report": {"status": "passed"},
            "runtime_execution_audit": {
                "status": "fail",
                "blocking_errors": ["missing event_table.csv"],
            },
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "failed"

    @pytest.mark.asyncio
    async def test_failed_status_when_module_coverage_missing(self, workspace: Path) -> None:
        """A patch is not enough without all coarse module agents."""
        state = {
            "job_id": "test_all_pass",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/Test.cc", "new_content": "// test"},
                ],
            },
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "failed"
