"""P0-8: cross_file_hard_gate rejects content field in changed_files."""

from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_hard_gate import (
    run_cross_file_hard_gate,
)


def test_content_field_rejected():
    """File with 'content' field must fail."""
    patch = {
        "changed_files": [
            {
                "path": "include/X.hh",
                "content": "#pragma once",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
        ],
    }
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("content" in e for e in result["errors"])


def test_content_with_new_content_also_rejected():
    """File with both 'content' and 'new_content' must fail."""
    patch = {
        "changed_files": [
            {
                "path": "include/X.hh",
                "content": "old",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
        ],
    }
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("content" in e for e in result["errors"])


def test_only_new_content_passes_content_check():
    """File with only 'new_content' should not fail on content check."""
    patch = {
        "changed_files": [
            {
                "path": "include/X.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
        ],
    }
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    content_errors = [e for e in result["errors"] if "content" in e.lower()]
    assert len(content_errors) == 0
