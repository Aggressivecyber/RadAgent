"""Cross-file LLM gate should review persisted module gate summaries."""

from __future__ import annotations

import json

from agent_core.g4_codegen.integration.cross_file_llm_gate import (
    _complete_module_gate_results_from_disk,
)


def test_complete_module_gate_results_from_disk(tmp_path) -> None:
    codegen_dir = tmp_path / "06_codegen"
    gate_dir = codegen_dir / "module_gates"
    gate_dir.mkdir(parents=True)
    (gate_dir / "geometry_hard_gate.json").write_text(
        json.dumps({"module_name": "geometry", "status": "pass"})
    )
    (gate_dir / "geometry_llm_gate.json").write_text(
        json.dumps({"module_name": "geometry", "status": "pass"})
    )
    (gate_dir / "main_cmake_hard_gate.json").write_text(
        json.dumps({"module_name": "main_cmake", "status": "pass"})
    )
    (gate_dir / "main_cmake_llm_gate.json").write_text(
        json.dumps({"module_name": "main_cmake", "status": "pass"})
    )

    completed = _complete_module_gate_results_from_disk(
        {"material": {"hard": {"status": "pass"}, "llm": {"status": "pass"}}},
        codegen_dir,
    )

    assert completed["material"]["hard"]["status"] == "pass"
    assert completed["geometry"]["hard"]["status"] == "pass"
    assert completed["geometry"]["llm"]["status"] == "pass"
    assert completed["main_cmake"]["hard"]["status"] == "pass"
    assert completed["main_cmake"]["llm"]["status"] == "pass"
