"""Test that persist_codegen_output marks status='failed' when static_semantic_scan fails."""

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


class TestPersistMarksFailedOnStaticScanFail:
    """Verify persist_codegen_output sets status='failed' on static scan failure."""

    @pytest.mark.asyncio
    async def test_failed_status_on_static_scan_fail(self, workspace: Path) -> None:
        """When static scan fails, g4_codegen_status should be 'failed'."""
        state = {
            "job_id": "test_static_fail",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/Test.cc", "new_content": "// test"},
                ],
            },
            "static_semantic_scan": {
                "status": "fail",
                "error_count": 1,
                "findings": [
                    {"file": "src/Test.cc", "issue": "empty_include", "severity": "error"},
                ],
            },
            "cross_file_hard_gate": {"status": "pass"},
            "cross_file_llm_gate": {"status": "pass"},
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "failed"

    @pytest.mark.asyncio
    async def test_failed_status_when_module_coverage_missing(self, workspace: Path) -> None:
        """Scan/cross-gate pass is not enough without all module agents."""
        state = {
            "job_id": "test_all_pass",
            "run_mode": "strict",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/Test.cc", "new_content": "// test"},
                ],
            },
            "static_semantic_scan": {"status": "pass"},
            "cross_file_hard_gate": {"status": "pass"},
            "cross_file_llm_gate": {"status": "pass"},
        }

        result = await persist_codegen_output_node(state)

        assert result["g4_codegen_status"] == "failed"
