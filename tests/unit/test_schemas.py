"""Unit tests for schemas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.schemas.gate_result import create_gate_report, create_gate_result
from agent_core.schemas.rag_context_pack import RetrievedContext, compute_sufficiency
from agent_core.schemas.task_spec import validate_task_spec


class TestTaskSpec:
    """Tests for TaskSpec schema."""

    def test_valid_task_spec_creation(self):
        """Valid task spec should create successfully."""
        data = {
            "simulation_scope": ["geant4"],
            "particle": {
                "type": "proton",
                "energy_MeV": 10.0,
                "direction": [0.0, 0.0, 1.0],
                "events": 1000,
            },
            "target": {"material": "Si", "size_um": [1000.0, 1000.0, 300.0]},
            "outputs": ["dose_map"],
        }
        spec, errors = validate_task_spec(data)
        assert spec is not None, f"Errors: {errors}"
        assert not errors

    def test_invalid_task_spec(self):
        """Invalid task spec should return errors."""
        data = {}
        spec, errors = validate_task_spec(data)
        assert spec is None or len(errors) > 0

    def test_valid_minimal_task_spec(self):
        """Minimal task spec with only scope should create."""
        data = {"simulation_scope": ["geant4"], "outputs": ["dose_map"]}
        spec, errors = validate_task_spec(data)
        assert spec is not None, f"Errors: {errors}"


class TestGateResult:
    """Tests for GateResult schema."""

    def test_create_passing_gate(self):
        """Creating a passing gate result."""
        result = create_gate_result(0, "RAG Sufficiency", True, message="Score: 0.95")
        assert result.passed is True
        assert result.gate_id == 0

    def test_create_failing_gate(self):
        """Creating a failing gate result."""
        result = create_gate_result(
            3, "Patch Format", False, retry_node="write_code_patch"
        )
        assert result.passed is False
        assert result.retry_node == "write_code_patch"

    def test_create_gate_report(self):
        """Creating a gate report from multiple results."""
        results = [
            create_gate_result(0, "RAG", True, message="OK"),
            create_gate_result(1, "Task Spec", True, message="OK"),
            create_gate_result(2, "Sim IR", False, message="Missing field"),
        ]
        report = create_gate_report("job_test", results)
        assert report.job_id == "job_test"
        assert not report.overall_passed  # One failure


class TestRAGContextPack:
    """Tests for RAG context pack sufficiency scoring."""

    def test_sufficiency_with_all_context(self):
        """Full context should have high sufficiency score."""
        context = RetrievedContext(
            manual_snippets=[{"text": "manual content", "source": "g4_manual"}],
            example_code=[{"code": "// example", "source": "g4_examples"}],
            data_contracts=[{"name": "g4_output", "source": "contracts"}],
            error_cases=[],
            benchmark_cases=[],
        )
        report = compute_sufficiency(context)
        assert report.score >= 0.75
        assert report.decision in ("allow_rag", "needs_web")

    def test_sufficiency_with_no_context(self):
        """No context should have zero score."""
        context = RetrievedContext()
        report = compute_sufficiency(context)
        # Empty error_cases counts as "no_errors" -> +0.15
        assert report.score == 0.15
        assert report.decision == "block_no_context"

    def test_sufficiency_with_manual_only(self):
        """Only manual snippets should give score of 0.30 (manual) + 0.15 (no errors)."""
        context = RetrievedContext(
            manual_snippets=[{"text": "some manual", "source": "manual"}],
        )
        report = compute_sufficiency(context)
        assert report.score == pytest.approx(0.45)
        assert report.decision == "block_no_context"
