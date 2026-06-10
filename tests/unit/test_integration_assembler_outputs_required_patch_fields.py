"""P0-2: integration_assembler outputs all required patch fields."""

from __future__ import annotations

import pytest
from agent_core.g4_codegen.integration.integration_assembler import (
    assemble_proposed_patch,
)

PATCH_REQUIRED_FIELDS = {
    "patch_id",
    "job_id",
    "description",
    "change_type",
    "risk_level",
    "changed_files",
    "test_plan",
    "expected_outputs",
}


@pytest.fixture
def sample_module_results():
    return {
        "simulation_core": {
            "status": "generated",
            "generated_files": [
                {
                    "path": "include/MaterialRegistry.hh",
                    "new_content": "#pragma once\n",
                    "generated_by": "simulation_core_module_agent",
                    "module_name": "simulation_core",
                    "rationale": "test",
                },
            ],
        },
    }


def test_patch_has_all_required_fields(sample_module_results):
    patch = assemble_proposed_patch(sample_module_results, "job_001")
    missing = PATCH_REQUIRED_FIELDS - set(patch.keys())
    assert not missing, f"Missing fields: {sorted(missing)}"


def test_patch_has_metadata(sample_module_results):
    patch = assemble_proposed_patch(sample_module_results, "job_001")
    assert "metadata" in patch
    meta = patch["metadata"]
    assert "source" in meta
    assert meta["source"] == "g4_codegen_agent_modules"
    assert "module_agent_count" in meta
    assert "passed_module_count" in meta
    assert "failed_module_count" in meta


def test_changed_files_have_required_fields(sample_module_results):
    patch = assemble_proposed_patch(sample_module_results, "job_001")
    file_required = {
        "path",
        "operation",
        "new_content",
        "zone",
        "generated_by",
        "module_name",
    }
    for idx, f in enumerate(patch["changed_files"]):
        missing = file_required - set(f.keys())
        assert not missing, f"File {idx} missing: {sorted(missing)}"
