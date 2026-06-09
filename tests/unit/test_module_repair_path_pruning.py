from __future__ import annotations

from agent_core.g4_codegen.repair.module_repair_loop import (
    _postprocess_repaired_module_files,
    _prune_files_outside_module_contract,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _generated(path: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content="content",
        generated_by="geometry_module_agent",
        module_name="geometry",
        rationale="unit test",
    )


def test_repair_prunes_files_outside_module_contract() -> None:
    files_by_path = {
        "include/DetectorConstruction.hh": _generated("include/DetectorConstruction.hh"),
        "src/DetectorConstruction.cc": _generated("src/DetectorConstruction.cc"),
        "module_dependency.json": _generated("module_dependency.json"),
    }
    module_context = {
        "module_contract": {
            "output_files": [
                "include/DetectorConstruction.hh",
                "src/DetectorConstruction.cc",
            ]
        }
    }

    _prune_files_outside_module_contract("geometry", module_context, files_by_path)

    assert set(files_by_path) == {
        "include/DetectorConstruction.hh",
        "src/DetectorConstruction.cc",
    }


def test_repair_postprocess_merges_contract_dependencies() -> None:
    generated_files = [
        _generated("include/DetectorConstruction.hh"),
        _generated("src/DetectorConstruction.cc"),
    ]
    module_context = {"module_contract": {"dependencies": ["material", "placement"]}}

    _postprocess_repaired_module_files("geometry", module_context, generated_files)

    for file_entry in generated_files:
        assert file_entry.dependencies == ["material", "placement"]
