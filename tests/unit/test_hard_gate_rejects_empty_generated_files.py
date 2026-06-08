"""Test that hard gate rejects empty generated_files."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile


class TestHardGateRejectsEmptyGeneratedFiles:
    """Verify hard gate fails when generated_files is empty."""

    def test_empty_list_returns_fail(self) -> None:
        """Empty generated_files list should result in fail."""
        result = run_hard_gate_checks("test_module", [])

        assert result.status == "fail"
        assert any("empty" in e.lower() for e in result.errors)

    def test_non_empty_files_may_pass(self) -> None:
        """Non-empty generated_files with valid content should pass basic checks."""
        files = [
            GeneratedModuleFile(
                path="src/Test.cc",
                operation="create_or_replace",
                new_content='#include "Test.hh"\nint x = 1;\n',
                generated_by="test_module_agent",
                module_name="test_module",
                rationale="test",
            ),
            GeneratedModuleFile(
                path="include/Test.hh",
                operation="create_or_replace",
                new_content="#pragma once\nint x;\n",
                generated_by="test_module_agent",
                module_name="test_module",
                rationale="test",
            ),
        ]

        result = run_hard_gate_checks("test_module", files)
        # Should not fail due to empty files
        assert "generated_files is empty" not in " ".join(result.errors)
