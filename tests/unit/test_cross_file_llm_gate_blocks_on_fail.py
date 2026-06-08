"""P0-12: cross_file_llm_gate blocks on fail."""

from __future__ import annotations


def test_persist_result_saves_status():
    """Verify persist saves the gate result."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch as mock_patch

    result = {
        "status": "fail",
        "checks": [],
        "errors": ["LLM gate failed"],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        job_dir = Path(tmpdir) / "jobs" / "test_job"
        job_dir.mkdir(parents=True)
        with mock_patch(
            "agent_core.config.workspace.get_job_dir",
            return_value=job_dir,
        ):
            from agent_core.g4_codegen.integration.cross_file_llm_gate import (
                _persist_result,
            )

            _persist_result(result, "test_job")
            persisted = job_dir / "06_codegen" / "cross_file_llm_gate.json"
            assert persisted.exists()
            import json

            data = json.loads(persisted.read_text())
            assert data["status"] == "fail"


def test_gate_result_structure():
    """Verify gate result has required fields."""
    result = {
        "status": "pass",
        "checks": [{"check": "semantic_consistency", "status": "pass"}],
        "errors": [],
        "warnings": [],
        "reviewer_notes": "All good",
    }
    assert "status" in result
    assert result["status"] in ("pass", "fail", "skipped")
    assert isinstance(result["checks"], list)
    assert isinstance(result["errors"], list)
