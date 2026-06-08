"""Test that static scan failure blocks cross-file hard gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestStaticScanFailureBlocksCrossFileGate:
    """Verify that static scan failure routes to persist instead of cross_file_hard_gate."""

    def test_route_after_static_scan_fail(self) -> None:
        """When static scan fails, route should go to persist, not cross_file_hard_gate."""
        from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_static_scan

        state: G4CodegenSubgraphState = {
            "static_semantic_scan": {"status": "fail"},
        }

        next_node = _route_after_static_scan(state)
        assert next_node == "persist_codegen_output"

    def test_route_after_static_scan_pass(self) -> None:
        """When static scan passes, route should go to cross_file_hard_gate."""
        from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_static_scan

        state: G4CodegenSubgraphState = {
            "static_semantic_scan": {"status": "pass"},
        }

        next_node = _route_after_static_scan(state)
        assert next_node == "cross_file_hard_gate"

    def test_route_with_findings(self) -> None:
        """Static scan with error-level findings should route to persist."""
        from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_static_scan

        state: G4CodegenSubgraphState = {
            "static_semantic_scan": {
                "status": "fail",
                "error_count": 2,
                "findings": [
                    {"file": "test.cc", "issue": "empty_include", "severity": "error"},
                ],
            },
        }

        next_node = _route_after_static_scan(state)
        assert next_node == "persist_codegen_output"
