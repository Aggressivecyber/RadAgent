from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_llm_gate import (
    REQUIRED_MODULES,
    _build_module_gate_status_table,
)


def test_cross_file_status_table_reports_all_required_module_gates_pass() -> None:
    gate_results = {
        module_name: {
            "hard": {"status": "pass"},
            "llm": {"status": "pass", "scorecard": {"overall_score": 0.95}},
        }
        for module_name in REQUIRED_MODULES
    }

    table = _build_module_gate_status_table(gate_results)

    assert table["all_required_module_gates_pass"] is True
    assert table["missing_modules"] == []
    assert table["incomplete_modules"] == []
    assert {row["module_name"] for row in table["rows"]} == REQUIRED_MODULES
