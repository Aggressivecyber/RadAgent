"""E2E test — patch applies to 08_geant4 directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node
from agent_core.patching.nodes import apply_patch
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


class TestG4CodegenPatchAppliesTo08Geant4:
    """Verify that patches are written into the 08_geant4 directory."""

    @pytest.mark.asyncio
    async def test_patch_writes_to_08_geant4(self, workspace: Path) -> None:
        """Patch files should end up under the 08_geant4 directory."""
        # First, run persist to get the generated_code_dir
        state = {
            "job_id": "patch_apply_test",
            "run_mode": "dev",
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/TestDetector.cc",
                        "new_content": '#include "TestDetector.hh"\nint x = 1;\n',
                    },
                    {
                        "path": "include/TestDetector.hh",
                        "new_content": "#pragma once\nint x;\n",
                    },
                ],
            },
            "static_semantic_scan": {"status": "pass"},
            "cross_file_hard_gate": {"status": "pass"},
            "cross_file_llm_gate": {"status": "pass"},
        }

        persist_result = await persist_codegen_output_node(state)
        code_dir = persist_result["generated_code_dir"]

        # Verify code_dir ends with 08_geant4
        assert code_dir.endswith("08_geant4")

        # Now apply the patch
        apply_state = {
            "job_id": "patch_apply_test",
            "proposed_patch": state["proposed_patch"],
            "patch_review_result": {},
            "generated_code_dir": code_dir,
            "errors": [],
        }

        result = await apply_patch(apply_state)

        assert result["patch_status"] == "applied"

        # Verify files exist under 08_geant4
        assert (Path(code_dir) / "src" / "TestDetector.cc").exists()
        assert (Path(code_dir) / "include" / "TestDetector.hh").exists()

        # Verify content
        cc_content = (Path(code_dir) / "src" / "TestDetector.cc").read_text()
        assert "TestDetector.hh" in cc_content
