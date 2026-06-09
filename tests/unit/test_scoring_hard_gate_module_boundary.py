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


def test_scoring_hard_gate_rejects_new_scoring_manager() -> None:
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
                '#include "G4ScoringManager.hh"\n'
                "void InitializeScoring() {\n"
                "  auto* scoringManager = new G4ScoringManager();\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetScoringManager" in e for e in result.errors)


def test_scoring_hard_gate_rejects_direct_g4thitsmap_find() -> None:
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
                '#include "G4THitsMap.hh"\n'
                "void ReadScoring(G4THitsMap<double>* edepMap) {\n"
                "  auto it = edepMap->find(0);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4THitsMap find" in e for e in result.errors)


def test_scoring_hard_gate_allows_g4thitsmap_get_map_find() -> None:
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
                '#include "G4THitsMap.hh"\n'
                "void ReadScoring(G4THitsMap<double>* edepMap) {\n"
                "  auto it = edepMap->GetMap()->find(0);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert not any("G4THitsMap find" in e for e in result.errors)


def test_scoring_hard_gate_rejects_mesh_get_scorer() -> None:
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
                "void Read(auto* mesh) {\n"
                '  auto* scorer = mesh->GetScorer("edepScorer");\n'
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetScorer" in e for e in result.errors)


def test_scoring_hard_gate_rejects_dynamic_cast_hits_map() -> None:
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
                '#include "G4THitsMap.hh"\n'
                "void Read(void* scorer) {\n"
                "  auto* map = dynamic_cast<G4THitsMap<G4double>*>(scorer);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("dynamic_cast" in e for e in result.errors)


def test_scoring_hard_gate_requires_g4statdouble_for_score_map() -> None:
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
                "void Read(auto* mesh) {\n"
                "  auto scoreMap = mesh->GetScoreMap();\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4StatDouble" in e for e in result.errors)


def test_scoring_hard_gate_rejects_get_mesh_name() -> None:
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
                "void RecordScoring() {\n"
                "  auto name = scMgr->GetMeshName(iMesh);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetMeshName" in e for e in result.errors)


def test_scoring_hard_gate_rejects_get_mesh_by_name() -> None:
    result = run_scoring_hard_gate(
        [
            _file(
                "include/ScoringManager.hh",
                "#ifndef SCORINGMANAGER_HH\n#define SCORINGMANAGER_HH\n"
                '#include "G4String.hh"\n'
                "class ScoringManager { G4String fMeshName; };\n#endif\n",
            ),
            _file(
                "src/ScoringManager.cc",
                '#include "ScoringManager.hh"\n'
                "void RecordScoring() {\n"
                "  auto* mesh = scManager->GetMesh(fMeshName);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetMesh(0)" in e for e in result.errors)


def test_scoring_hard_gate_rejects_get_mesh_by_named_constant() -> None:
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
                "namespace { constexpr int kExpectedMeshIndex = 0; }\n"
                "void RecordScoring() {\n"
                "  auto* mesh = scManager->GetMesh(kExpectedMeshIndex);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetMesh(0)" in e for e in result.errors)


def test_scoring_hard_gate_rejects_get_score_map_nonconst_ref() -> None:
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
                "void RecordScoring() {\n"
                "  auto& scoreMap = mesh->GetScoreMap();\n"
                "  G4StatDouble stat;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetScoreMap() by value" in e for e in result.errors)


def test_scoring_hard_gate_rejects_get_element_center() -> None:
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
                "void RecordScoring() {\n"
                "  G4ThreeVector center;\n"
                "  mesh->GetElementCenter(copyNo, center);\n"
                "  G4StatDouble stat;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("GetElementCenter" in e for e in result.errors)
