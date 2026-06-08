from __future__ import annotations

from agent_core.g4_codegen.module_gates.physics_hard_gate import run_physics_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="physics_module_agent",
        module_name="physics",
        rationale="test",
    )


def test_physics_hard_gate_rejects_invalid_proton_cut_macro() -> None:
    result = run_physics_hard_gate(
        [
            _file(
                "include/PhysicsListFactoryWrapper.hh",
                "#ifndef PHYSICSLISTFACTORYWRAPPER_HH\n"
                "#define PHYSICSLISTFACTORYWRAPPER_HH\n"
                "class PhysicsListFactoryWrapper {};\n"
                "#endif\n",
            ),
            _file(
                "src/PhysicsListFactoryWrapper.cc",
                '#include "PhysicsListFactoryWrapper.hh"\n',
            ),
            _file(
                "macros/physics_list.mac",
                "/process/em/setCut 0.01 mm proton\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("/process/em/setCut" in error for error in result.errors)


def test_physics_hard_gate_allows_valid_run_cut_macro() -> None:
    result = run_physics_hard_gate(
        [
            _file(
                "include/PhysicsListFactoryWrapper.hh",
                "#ifndef PHYSICSLISTFACTORYWRAPPER_HH\n"
                "#define PHYSICSLISTFACTORYWRAPPER_HH\n"
                "class PhysicsListFactoryWrapper {};\n"
                "#endif\n",
            ),
            _file(
                "src/PhysicsListFactoryWrapper.cc",
                '#include "PhysicsListFactoryWrapper.hh"\n',
            ),
            _file(
                "macros/physics_list.mac",
                "/run/setCutForAGivenParticle proton 0.01 mm\n",
            ),
        ],
        module_status="generated",
    )

    assert not any("/process/em/setCut" in error for error in result.errors)


def test_physics_hard_gate_rejects_local_factory_in_create_physics_list() -> None:
    result = run_physics_hard_gate(
        [
            _file(
                "include/PhysicsListFactoryWrapper.hh",
                "#ifndef PHYSICSLISTFACTORYWRAPPER_HH\n"
                "#define PHYSICSLISTFACTORYWRAPPER_HH\n"
                "class PhysicsListFactoryWrapper {};\n"
                "#endif\n",
            ),
            _file(
                "src/PhysicsListFactoryWrapper.cc",
                '#include "PhysicsListFactoryWrapper.hh"\n'
                '#include "G4PhysListFactory.hh"\n'
                "G4VModularPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList() {\n"
                "  G4PhysListFactory factory;\n"
                '  return factory.GetReferencePhysList("FTFP_BERT");\n'
                "}\n",
            ),
            _file("macros/physics_list.mac", "/run/setCut 0.1 mm\n"),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("local G4PhysListFactory" in error for error in result.errors)


def test_physics_hard_gate_allows_delete_phrase_in_comment_only() -> None:
    result = run_physics_hard_gate(
        [
            _file(
                "include/PhysicsListFactoryWrapper.hh",
                "#pragma once\nclass PhysicsListFactoryWrapper {};\n",
            ),
            _file(
                "src/PhysicsListFactoryWrapper.cc",
                '#include "PhysicsListFactoryWrapper.hh"\n'
                "// Do not delete fPhysicsList; Geant4 owns it.\n"
                "G4VUserPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList() {\n"
                "  return fPhysicsList;\n"
                "}\n",
            ),
            _file("macros/physics_list.mac", "/run/setCut 0.1 mm\n"),
        ],
        module_status="generated",
    )

    assert result.status == "pass"


def test_physics_hard_gate_rejects_real_delete_statement() -> None:
    result = run_physics_hard_gate(
        [
            _file(
                "include/PhysicsListFactoryWrapper.hh",
                "#pragma once\nclass PhysicsListFactoryWrapper {};\n",
            ),
            _file(
                "src/PhysicsListFactoryWrapper.cc",
                '#include "PhysicsListFactoryWrapper.hh"\n'
                "PhysicsListFactoryWrapper::~PhysicsListFactoryWrapper() {\n"
                "  delete fPhysicsList;\n"
                "}\n",
            ),
            _file("macros/physics_list.mac", "/run/setCut 0.1 mm\n"),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("must not delete fPhysicsList" in error for error in result.errors)


def test_physics_hard_gate_rejects_two_argument_default_cut() -> None:
    result = run_physics_hard_gate(
        [
            _file(
                "include/PhysicsListFactoryWrapper.hh",
                "#pragma once\nclass PhysicsListFactoryWrapper {};\n",
            ),
            _file(
                "src/PhysicsListFactoryWrapper.cc",
                '#include "PhysicsListFactoryWrapper.hh"\n'
                "G4VUserPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList() {\n"
                "  fPhysicsList->SetDefaultCutValue(0.7*mm, \"gamma\");\n"
                "  return fPhysicsList;\n"
                "}\n",
            ),
            _file("macros/physics_list.mac", "/run/setCut 0.1 mm\n"),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("SetDefaultCutValue accepts one" in error for error in result.errors)
