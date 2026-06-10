from __future__ import annotations

from agent_core.g4_codegen.module_agents.base import _postprocess_generated_module_files
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(module_name: str, path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by=f"{module_name}_module_agent",
        module_name=module_name,
        rationale="test",
    )


def test_module_postprocess_leaves_agent_output_unchanged() -> None:
    original = (
        '#include "ScoringManager.hh"\n'
        "std::vector<ScoringRecord> ScoringManager::GetScoringRecords() {\n"
        "  if (true) { return; }\n"
        "  return {};\n"
        "}\n"
    )
    files = [_file("scoring", "src/ScoringManager.cc", original)]

    _postprocess_generated_module_files("scoring", files)

    assert files[0].new_content == original


def test_module_postprocess_does_not_rewrite_main_constructor() -> None:
    original = (
        "int main() {\n"
        "  auto* materialRegistry = MaterialRegistry::GetInstance();\n"
        "  auto* detector = new DetectorConstruction(materialRegistry);\n"
        "}\n"
    )
    files = [_file("runtime_app", "main.cc", original)]

    _postprocess_generated_module_files(
        "runtime_app",
        files,
        {"existing_generated_file_summaries": []},
    )

    assert files[0].new_content == original
