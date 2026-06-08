from __future__ import annotations

from agent_core.g4_codegen.module_gates.source_hard_gate import run_source_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="source_module_agent",
        module_name="source",
        rationale="test",
    )


def test_source_hard_gate_rejects_cm_position_for_mm_ir() -> None:
    result = run_source_hard_gate(
        [
            _file(
                "include/PrimaryGeneratorAction.hh",
                "#ifndef PRIMARYGENERATORACTION_HH\n#define PRIMARYGENERATORACTION_HH\n"
                "class PrimaryGeneratorAction {};\n#endif\n",
            ),
            _file(
                "src/PrimaryGeneratorAction.cc",
                '#include "PrimaryGeneratorAction.hh"\n'
                "void build() {\n"
                "  fParticleGun->SetParticlePosition(G4ThreeVector(0*cm, 0*cm, -80*cm));\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("source position must use mm" in error for error in result.errors)


def test_source_hard_gate_allows_mm_position() -> None:
    result = run_source_hard_gate(
        [
            _file(
                "include/PrimaryGeneratorAction.hh",
                "#ifndef PRIMARYGENERATORACTION_HH\n#define PRIMARYGENERATORACTION_HH\n"
                "class PrimaryGeneratorAction {};\n#endif\n",
            ),
            _file(
                "src/PrimaryGeneratorAction.cc",
                '#include "PrimaryGeneratorAction.hh"\n'
                "void build() {\n"
                "  fParticleGun->SetParticlePosition(G4ThreeVector(0*mm, 0*mm, -80*mm));\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "pass"
