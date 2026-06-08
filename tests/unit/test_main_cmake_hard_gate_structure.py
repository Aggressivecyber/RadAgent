from __future__ import annotations

from agent_core.g4_codegen.module_gates.main_cmake_hard_gate import run_main_cmake_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="main_cmake_module_agent",
        module_name="main_cmake",
        rationale="test",
    )


def test_main_cmake_hard_gate_rejects_glob_and_double_initialize() -> None:
    result = run_main_cmake_hard_gate(
        [
            _file(
                "CMakeLists.txt",
                "cmake_minimum_required(VERSION 3.16)\n"
                "project(RadAgentG4)\n"
                'file(GLOB SOURCES "src/*.cc")\n'
                "add_executable(RadAgentG4 ${SOURCES})\n",
            ),
            _file("main.cc", "int main() { runManager->Initialize(); }\n"),
            _file("macros/init.mac", "/run/initialize\n"),
            _file("macros/run.mac", "/run/beamOn 1\n"),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("CMakeLists.txt must explicitly list main.cc" in e for e in result.errors)
    assert "add_executable must include main.cc" in result.errors
    assert any("Do not call runManager->Initialize" in e for e in result.errors)


def test_main_cmake_hard_gate_accepts_explicit_sources_and_single_initialize() -> None:
    result = run_main_cmake_hard_gate(
        [
            _file(
                "CMakeLists.txt",
                "cmake_minimum_required(VERSION 3.16)\n"
                "project(RadAgentG4)\n"
                "# Explicit list of all source files; do not use file(GLOB).\n"
                "add_executable(RadAgentG4 main.cc src/DetectorConstruction.cc)\n",
            ),
            _file("main.cc", "int main() { return 0; }\n"),
            _file("macros/init.mac", "/run/initialize\n"),
            _file("macros/run.mac", "/run/beamOn 1\n"),
        ],
        module_status="generated",
    )

    assert result.status == "pass"


def test_main_cmake_hard_gate_rejects_src_main_cc() -> None:
    result = run_main_cmake_hard_gate(
        [
            _file(
                "CMakeLists.txt",
                "cmake_minimum_required(VERSION 3.16)\n"
                "project(RadAgentG4)\n"
                "add_executable(RadAgentG4 src/main.cc src/DetectorConstruction.cc)\n",
            ),
            _file("main.cc", "int main() { return 0; }\n"),
            _file("macros/init.mac", "/run/initialize\n"),
            _file("macros/run.mac", "/run/beamOn 1\n"),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert "CMakeLists.txt must list root main.cc, not src/main.cc" in result.errors
