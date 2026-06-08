"""P0-18: Mock provider returns repaired module for FAILURE_DIAGNOSIS."""

from __future__ import annotations

from agent_core.models.mock import call_mock_model
from agent_core.models.schemas import ModelProvider, ModelTask


def test_mock_diagnosis_returns_files():
    result = call_mock_model(
        ModelTask.FAILURE_DIAGNOSIS,
        {"module_name": "material"},
    )
    assert result.provider == ModelProvider.MOCK
    assert result.parsed_json is not None
    data = result.parsed_json
    assert data["status"] == "success"
    assert "generated_files" in data
    assert len(data["generated_files"]) > 0


def test_mock_diagnosis_files_have_new_content():
    result = call_mock_model(
        ModelTask.FAILURE_DIAGNOSIS,
        {"module_name": "geometry"},
    )
    data = result.parsed_json
    for f in data["generated_files"]:
        assert "new_content" in f
        assert f["new_content"]
        assert "content" not in f


def test_mock_diagnosis_has_fixes_applied():
    result = call_mock_model(
        ModelTask.FAILURE_DIAGNOSIS,
        {"module_name": "source"},
    )
    data = result.parsed_json
    assert "fixes_applied" in data
    assert len(data["fixes_applied"]) > 0
