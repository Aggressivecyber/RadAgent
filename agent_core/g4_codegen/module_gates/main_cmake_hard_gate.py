"""Main/CMake module hard gate."""

from __future__ import annotations

import re

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
    run_macro = by_path.get("macros/run.mac", "")

    checks: list[dict[str, str]] = []
    if cmake:
        cmake_code = _strip_cmake_comments(cmake)
        uses_glob = bool(re.search(r"\bfile\s*\(\s*GLOB\b", cmake_code))
        checks.append(
            {
                "check": "cmake_explicit_sources",
                "status": "fail" if uses_glob else "pass",
                "message": "CMakeLists.txt must explicitly list main.cc and generated src/*.cc",
            }
        )
        has_main = bool(re.search(r"(^|[\s\(\"])main\.cc([\s\)\"]|$)", cmake_code))
        checks.append(
            {
                "check": "cmake_adds_main_cc",
                "status": "pass" if has_main else "fail",
                "message": "add_executable must include main.cc",
            }
        )
        uses_src_main = bool(
            re.search(r"(^|[\s\(\"])src/main\.cc([\s\)\"]|$)", cmake_code)
        )
        checks.append(
            {
                "check": "cmake_uses_root_main_cc",
                "status": "fail" if uses_src_main else "pass",
                "message": "CMakeLists.txt must list root main.cc, not src/main.cc",
            }
        )

    main_code = _strip_cpp_comments(main)
    double_initialize = bool(
        main
        and init
        and "runManager->Initialize()" in main_code
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
    run_initialize_index = run_macro.find("/run/initialize")
    run_beam_on_index = run_macro.find("/run/beamOn")
    run_macro_initializes_before_beam = (
        bool(run_macro)
        and run_initialize_index >= 0
        and run_beam_on_index >= 0
        and run_initialize_index < run_beam_on_index
    )
    checks.append(
        {
            "check": "run_macro_initializes_before_beam_on",
            "status": "pass" if run_macro_initializes_before_beam else "fail",
            "message": (
                "macros/run.mac must contain /run/initialize before /run/beamOn "
                "because smoke tests execute run.mac directly"
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
    wrapper_vars = re.findall(
        r"\bPhysicsListFactoryWrapper\s*\*?\s+([A-Za-z_]\w*)\s*(?:=|;)",
        main,
    )
    wrapper_vars.extend(
        re.findall(
            r"\bauto\s*\*?\s+([A-Za-z_]\w*)\s*=\s*new\s+PhysicsListFactoryWrapper\s*\(",
            main,
        )
    )
    passes_wrapper_directly = bool(
        re.search(
            r"SetUserInitialization\s*\(\s*new\s+PhysicsListFactoryWrapper\s*\(",
            main,
        )
    ) or any(
        re.search(rf"SetUserInitialization\s*\(\s*{re.escape(var)}\s*\)", main)
        for var in wrapper_vars
    )
    checks.append(
        {
            "check": "main_sets_physics_list_not_wrapper",
            "status": "fail" if passes_wrapper_directly else "pass",
            "message": (
                "main.cc must pass PhysicsListFactoryWrapper::CreatePhysicsList() "
                "result to SetUserInitialization, not the wrapper object"
            ),
        }
    )
    output_manager_as_action = bool(
        re.search(
            r"SetUserAction\s*\(\s*static_cast\s*<\s*G4User(?:Run|Event|Stepping)Action\s*\*"
            r">\s*\(\s*[A-Za-z_]\w*\s*\)\s*\)",
            main,
        )
    )
    checks.append(
        {
            "check": "main_does_not_register_output_manager_as_action",
            "status": "fail" if output_manager_as_action else "pass",
            "message": (
                "main.cc must not register OutputManager as a Geant4 user action; "
                "register real RunAction/EventAction/SteppingAction via ActionInitialization"
            ),
        }
    )
    defines_inline_actions = bool(
        re.search(
            r"\bclass\s+[A-Za-z_]\w*\s*:\s*public\s+"
            r"(?:G4UserRunAction|G4UserEventAction|G4UserSteppingAction|"
            r"G4VUserActionInitialization)\b",
            main,
        )
    )
    checks.append(
        {
            "check": "main_does_not_define_action_classes",
            "status": "fail" if defines_inline_actions else "pass",
            "message": (
                "main.cc must not define RunAction/EventAction/SteppingAction/"
                "ActionInitialization classes; use the action_initialization module"
            ),
        }
    )
    main_calls_runtime_singletons = bool(
        re.search(r"\b(?:OutputManager|ScoringManager)::Instance\s*\(", main)
    )
    checks.append(
        {
            "check": "main_does_not_call_output_or_scoring_singletons",
            "status": "fail" if main_calls_runtime_singletons else "pass",
            "message": (
                "main.cc must not call OutputManager::Instance() or "
                "ScoringManager::Instance(); user action modules own those calls"
            ),
        }
    )
    uses_action_initialization = bool(
        re.search(r"#include\s+[<\"]ActionInitialization\.hh[>\"]", main)
        and re.search(
            r"SetUserInitialization\s*\(\s*(?:new\s+)?ActionInitialization\b",
            main,
        )
    )
    checks.append(
        {
            "check": "main_registers_action_initialization_module",
            "status": "pass" if uses_action_initialization else "fail",
            "message": (
                "main.cc must include ActionInitialization.hh and register "
                "new ActionInitialization() with the run manager"
            ),
        }
    )

    result.checks.extend(checks)
    for check in checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])


def _strip_cmake_comments(content: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in content.splitlines())


def _strip_cpp_comments(content: str) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"//.*", "", without_block_comments)
