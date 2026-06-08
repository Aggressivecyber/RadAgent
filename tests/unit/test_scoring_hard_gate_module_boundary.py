from __future__ import annotations

from agent_core.g4_codegen.module_gates.scoring_hard_gate import run_scoring_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="scoring_module_agent",
        module_name="scoring",
        rationale="test",
    )


def test_scoring_hard_gate_rejects_geometry_and_placeholder_scorers() -> None:
    result = run_scoring_hard_gate(
        [
            _file(
                "include/ScoringManager.hh",
                "#ifndef SCORINGMANAGER_HH\n#define SCORINGMANAGER_HH\n"
                "class ScoringManager {};\n#endif\n",
            ),
            _file(
                "src/ScoringManager.cc",
                '#include "ScoringManager.hh"\n'
                '#include "G4PVPlacement.hh"\n'
                '#include "G4Box.hh"\n'
                "void ScoringManagerBuild() {\n"
                '  auto* cellFlux = new G4PSDoseDeposit("CellFlux");\n'
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4PVPlacement" in e for e in result.errors)
    assert any("G4Box" in e for e in result.errors)
    assert any("G4PSCellFlux" in e for e in result.errors)


def test_scoring_hard_gate_rejects_file_output() -> None:
    result = run_scoring_hard_gate(
        [
            _file(
                "include/ScoringManager.hh",
                "#ifndef SCORINGMANAGER_HH\n#define SCORINGMANAGER_HH\n"
                "class ScoringManager {};\n#endif\n",
            ),
            _file(
                "src/ScoringManager.cc",
                '#include "ScoringManager.hh"\n'
                "#include <fstream>\n"
                "void WriteScoringCsv() { std::ofstream csv(\"score.csv\"); }\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("must not write files" in e for e in result.errors)


def test_scoring_hard_gate_rejects_output_manager_calls() -> None:
    result = run_scoring_hard_gate(
        [
            _file(
                "include/ScoringManager.hh",
                "#ifndef SCORINGMANAGER_HH\n#define SCORINGMANAGER_HH\n"
                "class ScoringManager {};\n#endif\n",
            ),
            _file(
                "src/ScoringManager.cc",
                '#include "ScoringManager.hh"\n'
                '#include "OutputManager.hh"\n'
                "void RecordScoring() { OutputManager::Instance()->WriteEvent(nullptr); }\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("must not write files" in e for e in result.errors)
