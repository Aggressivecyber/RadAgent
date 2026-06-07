"""Test that persist_codegen_output_node returns generated_code_dir ending in 08_geant4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestGeneratedCodeDirPointsTo08Geant4:
    """Verify persist_codegen_output_node returns correct generated_code_dir."""

    @pytest.mark.asyncio
    async def test_dir_ends_with_08_geant4(self, workspace: Path) -> None:
        """generated_code_dir must end with 08_geant4."""
        from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node

        state = {
            "job_id": "test_dir_job",
            "run_mode": "dev",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            },
            "static_semantic_scan": {"status": "pass"},
            "cross_file_hard_gate": {"status": "pass"},
            "cross_file_llm_gate": {"status": "pass"},
        }

        result = await persist_codegen_output_node(state)

        assert result["generated_code_dir"].endswith("08_geant4"), (
            f"generated_code_dir should end with '08_geant4', got: {result['generated_code_dir']}"
        )

    @pytest.mark.asyncio
    async def test_dir_is_absolute(self, workspace: Path) -> None:
        """generated_code_dir should be an absolute path."""
        from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node

        state = {
            "job_id": "test_abs_job",
            "run_mode": "dev",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            },
            "static_semantic_scan": {"status": "pass"},
            "cross_file_hard_gate": {"status": "pass"},
            "cross_file_llm_gate": {"status": "pass"},
        }

        result = await persist_codegen_output_node(state)

        assert Path(result["generated_code_dir"]).is_absolute()
