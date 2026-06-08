"""E2E test — static scan failure blocks patch."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.g4_codegen.graph_nodes import (
    persist_codegen_output_node,
)
from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_static_scan
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


class TestG4CodegenStaticScanBlocksPatch:
    """Verify that static scan failure blocks the patch pipeline."""

    def test_scan_detects_empty_include(self) -> None:
        """Static scan should detect empty #include."""
        patch = {
            "changed_files": [
                {
                    "path": "src/Bad.cc",
                    "new_content": "#include\nint main() { return 0; }\n",
                },
            ],
        }

        scan = scan_generated_code(patch, "scan_block_test")
        assert scan["status"] == "fail"
        assert scan["error_count"] > 0

    def test_scan_detects_content_field(self) -> None:
        """Static scan should detect deprecated 'content' field."""
        patch = {
            "changed_files": [
                {
                    "path": "src/Old.cc",
                    "content": "old-style content field",
                },
            ],
        }

        scan = scan_generated_code(patch, "content_field_test")
        assert scan["status"] == "fail"

    def test_scan_detects_markdown_fence(self) -> None:
        """Static scan should detect Markdown fences in code."""
        patch = {
            "changed_files": [
                {
                    "path": "src/Fenced.cc",
                    "new_content": "```cpp\nint main() {}\n```\n",
                },
            ],
        }

        scan = scan_generated_code(patch, "fence_test")
        findings_issues = [f["issue"] for f in scan["findings"]]
        assert "markdown_fence" in findings_issues

    @pytest.mark.asyncio
    async def test_persist_marks_failed_on_scan_fail(self, workspace: Path) -> None:
        """When scan fails, persist should set status='failed'."""
        state = {
            "job_id": "scan_fail_persist",
            "run_mode": "dev",
            "proposed_patch": {
                "changed_files": [
                    {"path": "src/Bad.cc", "new_content": "#include\n"},
                ],
            },
            "static_semantic_scan": {"status": "fail", "error_count": 1},
            "cross_file_hard_gate": {"status": "pass"},
            "cross_file_llm_gate": {"status": "pass"},
        }

        result = await persist_codegen_output_node(state)
        assert result["g4_codegen_status"] == "failed"

    def test_route_after_scan_fail_goes_to_persist(self) -> None:
        """After static scan fail, route should go to persist, not cross_file_hard_gate."""
        state: G4CodegenSubgraphState = {
            "static_semantic_scan": {"status": "fail"},
        }

        next_node = _route_after_static_scan(state)
        assert next_node == "persist_codegen_output"
