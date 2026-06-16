"""The integration assembler must force the canonical B1-derived CMakeLists."""
from __future__ import annotations

from agent_core.g4_codegen.cmake_template import RADAGENT_CMAKE_TEMPLATE
from agent_core.g4_codegen.integration.integration_assembler import (
    assemble_proposed_patch,
)


def test_assembler_overrides_model_cmake_with_canonical_template(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    module_results = {
        "runtime_app": {
            "status": "generated",
            "generated_files": [
                {"path": "CMakeLists.txt", "new_content": "# model invented CMake", "operation": "create"},
                {"path": "src/main.cc", "new_content": "int main(){}", "operation": "create"},
            ],
        }
    }
    patch = assemble_proposed_patch(module_results, "job_x")
    cmake = [c for c in patch["changed_files"] if c["path"] == "CMakeLists.txt"][0]
    assert cmake["new_content"] == RADAGENT_CMAKE_TEMPLATE
    assert cmake["generated_by"] == "canonical_cmake_template"
    assert "file(GLOB sources" in cmake["new_content"]
    assert "CMAKE_CXX_STANDARD 17" in cmake["new_content"]
    # the non-CMake file is preserved untouched
    assert any(c["path"] == "src/main.cc" for c in patch["changed_files"])


def test_assembler_injects_cmake_when_model_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    module_results = {"runtime_app": {"status": "generated", "generated_files": [
        {"path": "src/main.cc", "new_content": "int main(){}", "operation": "create"}]}}
    patch = assemble_proposed_patch(module_results, "job_y")
    cmakes = [c for c in patch["changed_files"] if c["path"] == "CMakeLists.txt"]
    assert len(cmakes) == 1
    assert cmakes[0]["new_content"] == RADAGENT_CMAKE_TEMPLATE
