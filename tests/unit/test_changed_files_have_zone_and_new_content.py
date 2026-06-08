"""P0-3: Every changed_file has zone and new_content."""

from __future__ import annotations

import pytest

from agent_core.g4_codegen.integration.integration_assembler import (
    assemble_proposed_patch,
)


@pytest.fixture
def module_results():
    return {
        "material": {
            "status": "generated",
            "generated_files": [
                {
                    "path": "include/MaterialRegistry.hh",
                    "new_content": "#pragma once\n#include <string>\n",
                    "generated_by": "material_module_agent",
                    "module_name": "material",
                    "rationale": "test",
                },
                {
                    "path": "src/MaterialRegistry.cc",
                    "new_content": '#include "MaterialRegistry.hh"\n',
                    "generated_by": "material_module_agent",
                    "module_name": "material",
                    "rationale": "test",
                },
            ],
        },
    }


def test_all_files_have_zone(module_results):
    gate = {"material": {"hard": {"status": "pass"}, "llm": {"status": "pass"}}}
    patch = assemble_proposed_patch(module_results, gate, "job_001")
    for f in patch["changed_files"]:
        assert "zone" in f, f"Missing zone in {f.get('path')}"
        assert f["zone"] == "green"


def test_all_files_have_new_content(module_results):
    gate = {"material": {"hard": {"status": "pass"}, "llm": {"status": "pass"}}}
    patch = assemble_proposed_patch(module_results, gate, "job_001")
    for f in patch["changed_files"]:
        assert "new_content" in f, f"Missing new_content in {f.get('path')}"
        assert f["new_content"], f"Empty new_content in {f.get('path')}"


def test_no_content_field(module_results):
    gate = {"material": {"hard": {"status": "pass"}, "llm": {"status": "pass"}}}
    patch = assemble_proposed_patch(module_results, gate, "job_001")
    for f in patch["changed_files"]:
        assert "content" not in f, f"Deprecated 'content' in {f.get('path')}"
