"""P0-2/P0-3: cross_file_hard_gate requires CMakeLists.txt and main.cc."""

from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_hard_gate import (
    run_cross_file_hard_gate,
)


def test_missing_cmake_fails():
    patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": "int main(){return 0;}",
                "zone": "green",
                "module_name": "main_cmake",
                "generated_by": "m",
            },
            {
                "path": "include/X.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
            {
                "path": "src/X.cc",
                "new_content": '#include "X.hh"',
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
            {
                "path": "include/Y.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "geometry",
                "generated_by": "m",
            },
            {
                "path": "src/Y.cc",
                "new_content": '#include "Y.hh"',
                "zone": "green",
                "module_name": "geometry",
                "generated_by": "m",
            },
            {
                "path": "include/Z.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "placement",
                "generated_by": "m",
            },
            {
                "path": "src/Z.cc",
                "new_content": '#include "Z.hh"',
                "zone": "green",
                "module_name": "placement",
                "generated_by": "m",
            },
            {
                "path": "include/W.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "source",
                "generated_by": "m",
            },
            {
                "path": "src/W.cc",
                "new_content": '#include "W.hh"',
                "zone": "green",
                "module_name": "source",
                "generated_by": "m",
            },
            {
                "path": "include/P.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "physics",
                "generated_by": "m",
            },
            {
                "path": "src/P.cc",
                "new_content": '#include "P.hh"',
                "zone": "green",
                "module_name": "physics",
                "generated_by": "m",
            },
            {
                "path": "macros/p.mac",
                "new_content": "/run/initialize",
                "zone": "green",
                "module_name": "physics",
                "generated_by": "m",
            },
            {
                "path": "include/SD.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "sensitive_detector",  # noqa: E501
                "generated_by": "m",
            },
            {
                "path": "src/SD.cc",
                "new_content": '#include "SD.hh"',
                "zone": "green",
                "module_name": "sensitive_detector",
                "generated_by": "m",
            },
            {
                "path": "include/SC.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "scoring",
                "generated_by": "m",
            },
            {
                "path": "src/SC.cc",
                "new_content": '#include "SC.hh"',
                "zone": "green",
                "module_name": "scoring",
                "generated_by": "m",
            },
            {
                "path": "include/OM.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "output_manager",
                "generated_by": "m",
            },
            {
                "path": "src/OM.cc",
                "new_content": '#include "OM.hh"',
                "zone": "green",
                "module_name": "output_manager",
                "generated_by": "m",
            },
            {
                "path": "include/AI.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "action_initialization",
                "generated_by": "m",
            },
            {
                "path": "src/AI.cc",
                "new_content": '#include "AI.hh"',
                "zone": "green",
                "module_name": "action_initialization",
                "generated_by": "m",
            },
        ],
    }
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("CMakeLists.txt" in e for e in result["errors"])


def test_missing_main_cc_fails():
    patch = {
        "changed_files": [
            {
                "path": "CMakeLists.txt",
                "new_content": "cmake_minimum_required(VERSION 3.16)",
                "zone": "green",
                "module_name": "main_cmake",
                "generated_by": "m",
            },
            {
                "path": "include/X.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
            {
                "path": "src/X.cc",
                "new_content": '#include "X.hh"',
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            },
            {
                "path": "include/Y.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "geometry",
                "generated_by": "m",
            },
            {
                "path": "src/Y.cc",
                "new_content": '#include "Y.hh"',
                "zone": "green",
                "module_name": "geometry",
                "generated_by": "m",
            },
            {
                "path": "include/Z.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "placement",
                "generated_by": "m",
            },
            {
                "path": "src/Z.cc",
                "new_content": '#include "Z.hh"',
                "zone": "green",
                "module_name": "placement",
                "generated_by": "m",
            },
            {
                "path": "include/W.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "source",
                "generated_by": "m",
            },
            {
                "path": "src/W.cc",
                "new_content": '#include "W.hh"',
                "zone": "green",
                "module_name": "source",
                "generated_by": "m",
            },
            {
                "path": "include/P.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "physics",
                "generated_by": "m",
            },
            {
                "path": "src/P.cc",
                "new_content": '#include "P.hh"',
                "zone": "green",
                "module_name": "physics",
                "generated_by": "m",
            },
            {
                "path": "macros/p.mac",
                "new_content": "/run/initialize",
                "zone": "green",
                "module_name": "physics",
                "generated_by": "m",
            },
            {
                "path": "include/SD.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "sensitive_detector",
                "generated_by": "m",
            },
            {
                "path": "src/SD.cc",
                "new_content": '#include "SD.hh"',
                "zone": "green",
                "module_name": "sensitive_detector",
                "generated_by": "m",
            },
            {
                "path": "include/SC.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "scoring",
                "generated_by": "m",
            },
            {
                "path": "src/SC.cc",
                "new_content": '#include "SC.hh"',
                "zone": "green",
                "module_name": "scoring",
                "generated_by": "m",
            },
            {
                "path": "include/OM.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "output_manager",
                "generated_by": "m",
            },
            {
                "path": "src/OM.cc",
                "new_content": '#include "OM.hh"',
                "zone": "green",
                "module_name": "output_manager",
                "generated_by": "m",
            },
            {
                "path": "include/AI.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": "action_initialization",
                "generated_by": "m",
            },
            {
                "path": "src/AI.cc",
                "new_content": '#include "AI.hh"',
                "zone": "green",
                "module_name": "action_initialization",
                "generated_by": "m",
            },
        ],
    }
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("main.cc" in e for e in result["errors"])


def test_both_present_passes():
    """Both CMakeLists.txt and main.cc present — should not fail on those checks."""
    from agent_core.g4_codegen.integration.cross_file_hard_gate import REQUIRED_MODULES

    files = [
        {
            "path": "CMakeLists.txt",
            "new_content": "cmake_minimum_required(VERSION 3.16)\nproject(t)\nfind_package(Geant4 REQUIRED)\nfile(GLOB s src/*.cc)\nadd_executable(app main.cc ${s})\n",  # noqa: E501
            "zone": "green",
            "module_name": "main_cmake",
            "generated_by": "m",
        },
        {
            "path": "main.cc",
            "new_content": "int main(){return 0;}",
            "zone": "green",
            "module_name": "main_cmake",
            "generated_by": "m",
        },
    ]
    for mod in REQUIRED_MODULES:
        if mod == "main_cmake":
            continue
        files.append(
            {
                "path": f"include/{mod}.hh",
                "new_content": "#pragma once",
                "zone": "green",
                "module_name": mod,
                "generated_by": "m",
            }
        )
        files.append(
            {
                "path": f"src/{mod}.cc",
                "new_content": f'#include "{mod}.hh"',
                "zone": "green",
                "module_name": mod,
                "generated_by": "m",
            }
        )
    result = run_cross_file_hard_gate({"changed_files": files}, {}, "test_job")
    cmake_check = [c for c in result["checks"] if c["check"] == "cmake_exists"]
    main_check = [c for c in result["checks"] if c["check"] == "main_cc_exists"]
    assert cmake_check[0]["status"] == "pass"
    assert main_check[0]["status"] == "pass"
