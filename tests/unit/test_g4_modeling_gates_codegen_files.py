from __future__ import annotations

from pathlib import Path

from agent_core.gates.g4_modeling_gates import run_g4_modeling_gates

from tests.real_g4_modules.common import build_real_g4_model_ir


async def test_g4_codegen_file_gates_run_without_skipping(tmp_path: Path) -> None:
    g4_dir = tmp_path / "08_geant4"
    (g4_dir / "include").mkdir(parents=True)
    (g4_dir / "src").mkdir()
    (g4_dir / "include" / "Example.hh").write_text(
        "#pragma once\nclass Example { public: void Run(); };\n",
        encoding="utf-8",
    )
    (g4_dir / "src" / "Example.cc").write_text(
        '#include "Example.hh"\nvoid Example::Run() {}\n',
        encoding="utf-8",
    )

    result = await run_g4_modeling_gates(
        {
            "job_id": "unit_codegen_file_gates",
            "gate_results": [],
            "failed_gates": [],
            "g4_model_ir": build_real_g4_model_ir("unit_codegen_file_gates"),
            "generated_code_dir": str(g4_dir),
        }
    )

    gates = {gate["gate_id"]: gate for gate in result["gate_results"]}
    assert gates[17]["status"] == "pass"
    assert gates[18]["status"] == "pass"
    assert gates[17]["status"] != "skipped"
    assert gates[18]["status"] != "skipped"


async def test_g4_codegen_file_gates_fail_when_code_missing() -> None:
    result = await run_g4_modeling_gates(
        {
            "job_id": "unit_codegen_file_gates_missing",
            "gate_results": [],
            "failed_gates": [],
            "g4_model_ir": build_real_g4_model_ir("unit_codegen_file_gates_missing"),
            "generated_code_dir": "",
        }
    )

    gates = {gate["gate_id"]: gate for gate in result["gate_results"]}
    assert gates[17]["status"] == "fail"
    assert gates[18]["status"] == "fail"
