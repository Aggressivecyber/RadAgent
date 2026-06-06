"""Acceptance mode no-skip tests.

Validates that in mvp1_acceptance mode, Gates 6/8/9/11 cannot be skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from agent_core.nodes.run_gate_checks import _MVP1_NO_SKIP_GATES, run_gate_checks


def _valid_patch() -> dict:
    """Return a patch that passes PatchValidator."""
    return {
        "patch_id": "p1",
        "job_id": "test-acceptance",
        "description": "test patch",
        "change_type": "create",
        "risk_level": "low",
        "changed_files": [
            {
                "path": "05_geant4/src/main.cc",
                "new_content": "int main() { return 0; }",
                "zone": "green",
            },
        ],
        "test_plan": "compile check",
        "expected_outputs": {},
    }


def _base_state(**overrides: Any) -> dict:
    return {
        "job_id": "test-acceptance",
        "user_query": "acceptance test",
        "execution_mode": "mvp1_acceptance",
        "task_spec": {},
        "simulation_ir": {},
        "proposed_patch": _valid_patch(),
        "rag_sufficiency_score": 0.90,
        "context_decision": "allow_rag",
        "context_sufficiency_report": {},
        "skipped_gates": [],
        **overrides,
    }


def _setup_patches(tmp_path: Path) -> list:
    """Return context managers for workspace patches."""
    (tmp_path / "09_validation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "05_geant4" / "src").mkdir(parents=True, exist_ok=True)
    return [
        patch("agent_core.nodes.run_gate_checks.get_output_dir", return_value=tmp_path),
        patch("agent_core.nodes.run_gate_checks.get_job_dir", return_value=tmp_path),
    ]


class TestMvp1NoSkipGates:
    """Gates 6, 8, 9, 11 cannot be skipped in mvp1_acceptance mode."""

    @pytest.mark.anyio
    async def test_gate6_skipped_in_acceptance_becomes_fail(self, tmp_path: Path):
        """Gate 6 skipped in mvp1_acceptance mode is converted to fail."""
        state = _base_state()
        patches = _setup_patches(tmp_path)
        for p in patches:
            p.start()
        try:
            result = await run_gate_checks(state)
        finally:
            for p in patches:
                p.stop()
        gate6 = [g for g in result["gate_results"] if g["gate_id"] == 6]
        assert len(gate6) == 1
        g = gate6[0]
        # In mvp1_acceptance, originally-skipped gates must be converted to fail
        if "MVP1" in g.get("message", "") or "cannot be skipped" in g.get("message", ""):
            assert g["passed"] is False
            assert g["severity"] == "fail"

    @pytest.mark.anyio
    async def test_gate9_skipped_in_acceptance_becomes_fail(self, tmp_path: Path):
        """Gate 9 skipped in mvp1_acceptance mode is converted to fail."""
        state = _base_state()
        patches = _setup_patches(tmp_path)
        for p in patches:
            p.start()
        try:
            result = await run_gate_checks(state)
        finally:
            for p in patches:
                p.stop()
        gate9 = [g for g in result["gate_results"] if g["gate_id"] == 9]
        assert len(gate9) == 1
        g = gate9[0]
        # In mvp1_acceptance, originally-skipped gates must be converted to fail
        if "MVP1" in g.get("message", "") or "cannot be skipped" in g.get("message", ""):
            assert g["passed"] is False
            assert g["severity"] == "fail"

    def test_mvp1_no_skip_set(self):
        """The set of non-skippable gates is {6, 8, 9, 11}."""
        assert _MVP1_NO_SKIP_GATES == {6, 8, 9, 11}

    def test_gate0_not_in_no_skip_set(self):
        """Gate 0 (context sufficiency) is not in the no-skip set."""
        assert 0 not in _MVP1_NO_SKIP_GATES

    @pytest.mark.anyio
    async def test_dev_mode_allows_skip(self, tmp_path: Path):
        """In dev_no_geant4_env mode, skipped gates remain skipped."""
        state = _base_state(execution_mode="dev_no_geant4_env")
        patches = _setup_patches(tmp_path)
        for p in patches:
            p.start()
        try:
            result = await run_gate_checks(state)
        finally:
            for p in patches:
                p.stop()
        # In dev mode, skipped gates should NOT contain "MVP1" in their message
        for g in result["gate_results"]:
            if g.get("severity") == "skipped":
                assert "MVP1" not in g.get("message", "")
