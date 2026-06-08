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
