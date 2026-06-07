"""Tests for Gate Runner status strategy and Gate 4 permission validation.

Verifies:
  - VERIFIED only when 0 failed + 0 skipped
  - PARTIAL when 0 failed but some skipped (dev mode)
  - FAILED when any gate fails
  - Gate 4 does NOT bare auto-pass
  - Gate 4 validates zone from patch data
  - Gate 4 skipped when no patch data available
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_core.gates.gate_runner import finalize_gate_results, load_gate_inputs
from agent_core.gates.base_gates import run_base_gates


class TestFinalizeStatusStrategy:
    """Verify finalize_gate_results status determination."""

    async def test_verified_when_all_passed_no_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """VERIFIED only when 0 failed AND 0 skipped."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "test_job" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job",
            "gate_results": [
                {"gate_id": 0, "name": "Context", "status": "pass"},
            ],
            "failed_gates": [],
            "skipped_gates": [],
        }
        result = await finalize_gate_results(state)
        assert result["validation_status"] == "VERIFIED"

    async def test_partial_when_skipped_but_no_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PARTIAL when 0 failed but some skipped (dev mode)."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "test_job2" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job2",
            "gate_results": [
                {"gate_id": 0, "name": "Context", "status": "pass"},
                {"gate_id": 7, "name": "Unit Test", "status": "skipped"},
            ],
            "failed_gates": [],
            "skipped_gates": [{"gate_id": 7, "reason": "dev mode"}],
        }
        result = await finalize_gate_results(state)
        assert result["validation_status"] == "PARTIAL"

    async def test_partial_when_few_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PARTIAL when ≤2 failures."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "test_job3" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job3",
            "gate_results": [
                {"gate_id": 5, "name": "Static Check", "status": "fail"},
            ],
            "failed_gates": ["Static Check"],
            "skipped_gates": [],
        }
        result = await finalize_gate_results(state)
        assert result["validation_status"] == "PARTIAL"

    async def test_failed_when_many_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FAILED when >2 failures."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "test_job4" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job4",
            "gate_results": [],
            "failed_gates": ["Gate A", "Gate B", "Gate C"],
            "skipped_gates": [],
        }
        result = await finalize_gate_results(state)
        assert result["validation_status"] == "FAILED"

    async def test_dev_mode_gates_produce_partial_not_verified(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dev mode with skipped gates should finalize as PARTIAL, never VERIFIED."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        state = {
            "job_id": "dev_test",
            "execution_mode": "dev_no_geant4_env",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        base_result = await run_base_gates(state)

        # Now finalize
        job_dir = tmp_path / "jobs" / "dev_test" / "09_validation"
        job_dir.mkdir(parents=True)
        finalize_state = {
            "job_id": "dev_test",
            **base_result,
        }
        result = await finalize_gate_results(finalize_state)

        # Must NOT be VERIFIED — dev mode always has skipped gates
        assert result["validation_status"] != "VERIFIED", (
            f"Dev mode returned VERIFIED despite skipped gates: "
            f"{base_result.get('skipped_gates', [])}"
        )


class TestGate4NoAutoPass:
    """Verify Gate 4 (File Permission) does NOT bare auto-pass."""

    async def test_gate4_skipped_when_no_patch_data(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Gate 4 must not auto-pass when no patch data is available."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "g4test" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "g4test",
            "execution_mode": "dev_no_geant4_env",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "applied_patch_path": "",
            "proposed_patch_path": "",
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)
        gate4 = [g for g in result["gate_results"] if g["gate_id"] == 4][0]

        # Must NOT be a bare "pass" with empty evidence
        assert gate4["status"] != "pass" or gate4.get("evidence"), (
            f"Gate 4 bare auto-passed: status={gate4['status']}, evidence={gate4.get('evidence')}"
        )

    async def test_gate4_validates_green_zone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Gate 4 must validate zones when patch data has changed_files."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "g4test2" / "09_validation"
        job_dir.mkdir(parents=True)

        # Create an applied_patch.json with green zone files
        patch_data = {
            "changed_files": [
                {"path": "src/test.cc", "zone": "green", "new_content": "// ok"},
                {"path": "include/test.hh", "zone": "green", "new_content": "// ok"},
            ]
        }
        applied_patch = job_dir / "applied_patch.json"
        applied_patch.write_text(json.dumps(patch_data))

        state = {
            "job_id": "g4test2",
            "execution_mode": "dev_no_geant4_env",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "applied_patch_path": str(applied_patch),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)
        gate4 = [g for g in result["gate_results"] if g["gate_id"] == 4][0]

        assert gate4["status"] == "pass", (
            f"Gate 4 should pass for green zone files: {gate4['failed_items']}"
        )
        assert gate4.get("evidence"), "Gate 4 must have evidence of zone check"

    async def test_gate4_fails_on_red_zone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Gate 4 must fail when patch contains red zone files."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "g4test3" / "09_validation"
        job_dir.mkdir(parents=True)

        # Create patch with red zone file
        patch_data = {
            "changed_files": [
                {"path": "src/test.cc", "zone": "green", "new_content": "// ok"},
                {"path": "/etc/passwd", "zone": "red", "new_content": "hacked"},
            ]
        }
        applied_patch = job_dir / "applied_patch.json"
        applied_patch.write_text(json.dumps(patch_data))

        state = {
            "job_id": "g4test3",
            "execution_mode": "dev_no_geant4_env",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "applied_patch_path": str(applied_patch),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        result = await run_base_gates(state)
        gate4 = [g for g in result["gate_results"] if g["gate_id"] == 4][0]

        assert gate4["status"] == "fail", (
            f"Gate 4 should fail for red zone files: {gate4}"
        )
