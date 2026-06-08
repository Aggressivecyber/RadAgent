"""Main/CMake module hard gate."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_main_cmake_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for main/CMake module."""
    result = run_hard_gate_checks(
        module_name="main_cmake",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[],
    )
    _append_main_cmake_checks(result, generated_files)
    return result


def _append_main_cmake_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    by_path = {f.path: f.new_content for f in generated_files}
    cmake = by_path.get("CMakeLists.txt", "")
    main = by_path.get("main.cc", "")
    init = by_path.get("macros/init.mac", "")

    checks: list[dict[str, str]] = []
    if cmake:
        uses_glob = "file(GLOB" in cmake or "file (GLOB" in cmake
        checks.append(
            {
                "check": "cmake_explicit_sources",
                "status": "fail" if uses_glob else "pass",
                "message": "CMakeLists.txt must explicitly list main.cc and generated src/*.cc",
            }
        )
        has_main = "add_executable" in cmake and "main.cc" in cmake
        checks.append(
            {
                "check": "cmake_adds_main_cc",
                "status": "pass" if has_main else "fail",
                "message": "add_executable must include main.cc",
            }
        )

    double_initialize = bool(
        main
        and init
        and "runManager->Initialize()" in main
        and "/run/initialize" in init
    )
    checks.append(
        {
            "check": "single_run_initialization_path",
            "status": "fail" if double_initialize else "pass",
            "message": (
                "Do not call runManager->Initialize() when init.mac also contains "
                "/run/initialize"
            ),
        }
    )
    if 'new PhysicsListFactoryWrapper("' in main:
        checks.append(
            {
                "check": "main_physics_wrapper_constructor_matches_contract",
                "status": "fail",
                "message": (
                    "main.cc must not call PhysicsListFactoryWrapper(string) unless "
                    "the physics module declares that constructor"
                ),
            }
        )

    result.checks.extend(checks)
    for check in checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])
