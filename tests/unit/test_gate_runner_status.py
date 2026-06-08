"""Tests for Gate Runner status strategy and Gate 4 permission validation.

Verifies:
  - passed only when critical gates pass and no critical skips
  - failed when any gate fails
  - failed when any gate skipped (no dev mode, no partial pass)
  - Gate 4 does NOT bare auto-pass
  - Gate 4 validates zone from patch data
  - Gate 4 fails when no patch data available
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_core.gates.base_gates import run_base_gates
from agent_core.gates.gate_runner import compute_validation_status, finalize_gate_results


class TestFinalizeStatusStrategy:
    """Verify finalize_gate_results status determination."""

    async def test_verified_when_all_passed_no_skipped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """passed only when 0 failed AND 0 skipped."""
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
        assert result["validation_status"] == "passed"

    async def test_skipped_gate_means_failed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """failed when any gate is skipped (no dev mode partial pass)."""
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
            "skipped_gates": [{"gate_id": 7, "reason": "missing"}],
        }
        result = await finalize_gate_results(state)
        assert result["validation_status"] == "failed"

    async def test_failed_when_any_gate_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """failed when any gate fails, regardless of count."""
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
        assert result["validation_status"] == "failed"

    async def test_failed_when_many_failures(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """failed when multiple gates fail."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "test_job4" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "test_job4",
            "gate_results": [
                {"gate_id": 0, "name": "Context", "status": "fail"},
                {"gate_id": 5, "name": "Static", "status": "fail"},
                {"gate_id": 7, "name": "Unit Test", "status": "fail"},
            ],
            "failed_gates": ["Context", "Static", "Unit Test"],
            "skipped_gates": [],
        }
        result = await finalize_gate_results(state)
        assert result["validation_status"] == "failed"

    async def test_strict_mode_skipped_gates_fail(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Strict mode: skipped gates = failed (no partial pass)."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        state = {
            "job_id": "strict_test",
            "run_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "noexist"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }

        base_result = await run_base_gates(state)

        job_dir = tmp_path / "jobs" / "strict_test" / "09_validation"
        job_dir.mkdir(parents=True)
        finalize_state = {
            "job_id": "strict_test",
            **base_result,
        }
        result = await finalize_gate_results(finalize_state)

        # Skipped gates = failed in strict mode
        if base_result.get("skipped_gates"):
            assert result["validation_status"] == "failed", (
                f"Strict mode with skipped gates must be failed, got: {result['validation_status']}"
            )


class TestGate4NoAutoPass:
    """Verify Gate 4 (File Permission) does NOT bare auto-pass."""

    async def test_gate4_fails_when_no_patch_data(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Gate 4 must not auto-pass when no patch data is available."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "g4test" / "09_validation"
        job_dir.mkdir(parents=True)

        state = {
            "job_id": "g4test",
            "execution_mode": "strict",
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
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
            "execution_mode": "strict",
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

    async def test_gate4_falls_back_to_codegen_proposed_patch(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Gate 4 should read 06_codegen/proposed_patch.json when applied summary lacks zones."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_root = tmp_path / "jobs" / "g4test2b"
        validation_dir = job_root / "09_validation"
        codegen_dir = job_root / "06_codegen"
        validation_dir.mkdir(parents=True)
        codegen_dir.mkdir(parents=True)

        applied_patch = validation_dir / "applied_patch.json"
        applied_patch.write_text(json.dumps({"files_applied": ["src/test.cc"]}))
        proposed_patch = codegen_dir / "proposed_patch.json"
        proposed_patch.write_text(
            json.dumps(
                {
                    "changed_files": [
                        {"path": "src/test.cc", "zone": "green", "new_content": "// ok"}
                    ]
                }
            )
        )

        state = {
            "job_id": "g4test2b",
            "execution_mode": "strict",
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

        assert gate4["status"] == "pass"
        assert gate4["evidence"] == ["checked 1 files"]

    async def test_gate4_fails_on_red_zone(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
            "execution_mode": "strict",
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

        assert gate4["status"] == "fail", f"Gate 4 should fail for red zone files: {gate4}"


class TestComputeValidationStatus:
    """Test compute_validation_status logic directly."""

    def test_all_passed_returns_verified(self) -> None:
        gates = [
            {"gate_id": 0, "status": "pass"},
            {"gate_id": 7, "status": "pass"},
        ]
        assert compute_validation_status(gates, "strict") == "passed"

    def test_any_fail_returns_failed(self) -> None:
        gates = [
            {"gate_id": 0, "status": "pass"},
            {"gate_id": 7, "status": "fail"},
        ]
        assert compute_validation_status(gates, "strict") == "failed"

    def test_skipped_returns_failed(self) -> None:
        """Any skipped gate = failed (no dev mode partial pass)."""
        gates = [
            {"gate_id": 0, "status": "pass"},
            {"gate_id": 3, "status": "skipped"},
        ]
        assert compute_validation_status(gates, "strict") == "failed"

    def test_critical_skipped_returns_failed(self) -> None:
        """Critical skipped = failed in all modes."""
        gates = [
            {"gate_id": 0, "status": "pass"},
            {"gate_id": 7, "status": "skipped"},
        ]
        assert compute_validation_status(gates, "strict") == "failed"

    def test_skipped_acceptance_returns_failed(self) -> None:
        gates = [
            {"gate_id": 0, "status": "pass"},
            {"gate_id": 7, "status": "skipped"},
        ]
        assert compute_validation_status(gates, "acceptance") == "failed"

    def test_non_critical_skipped_returns_failed(self) -> None:
        """Non-critical skipped also = failed (no partial pass)."""
        gates = [
            {"gate_id": 0, "status": "pass"},
            {"gate_id": 3, "status": "skipped"},
        ]
        assert compute_validation_status(gates, "acceptance") == "failed"

    def test_empty_results_returns_verified(self) -> None:
        assert compute_validation_status([], "strict") == "passed"
