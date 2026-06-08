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


def test_source_hard_gate_rejects_commented_out_event_parameter_used_in_body() -> None:
    result = run_source_hard_gate(
        [
            _file(
                "include/PrimaryGeneratorAction.hh",
                "#pragma once\n"
                "#include <G4VUserPrimaryGeneratorAction.hh>\n"
                "class G4Event;\n"
                "class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {\n"
                "public:\n"
                "  void GeneratePrimaries(G4Event* event) override;\n"
                "};\n",
            ),
            _file(
                "src/PrimaryGeneratorAction.cc",
                '#include "PrimaryGeneratorAction.hh"\n'
                "void PrimaryGeneratorAction::GeneratePrimaries(G4Event* /*event*/) {\n"
                "  fParticleGun->GeneratePrimaryVertex(event);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4Event* event" in error for error in result.errors)


def test_source_hard_gate_accepts_named_event_parameter() -> None:
    result = run_source_hard_gate(
        [
            _file(
                "include/PrimaryGeneratorAction.hh",
                "#pragma once\n"
                "#include <G4VUserPrimaryGeneratorAction.hh>\n"
                "class G4Event;\n"
                "class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {\n"
                "public:\n"
                "  void GeneratePrimaries(G4Event* event) override;\n"
                "};\n",
            ),
            _file(
                "src/PrimaryGeneratorAction.cc",
                '#include "PrimaryGeneratorAction.hh"\n'
                "void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event) {\n"
                "  fParticleGun->GeneratePrimaryVertex(event);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "pass"
