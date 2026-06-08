"""P0-14: effective ModuleContext contains previous module summaries."""

from __future__ import annotations

from agent_core.g4_codegen.graph_nodes import _extract_file_summary


def test_extract_file_summary_structure():
    """_extract_file_summary must return all required fields."""
    file_data = {
        "path": "include/MaterialRegistry.hh",
        "new_content": (
            "#pragma once\n"
            '#include "G4Material.hh"\n'
            "class MaterialRegistry {\n"
            "public:\n"
            "  G4Material* GetMaterial(const G4String& name);\n"
            "};\n"
        ),
        "generated_by": "material_module_agent",
        "module_name": "material",
    }
    summary = _extract_file_summary("material", file_data)

    assert summary["module_name"] == "material"
    assert summary["path"] == "include/MaterialRegistry.hh"
    assert summary["generated_by"] == "material_module_agent"
    assert "MaterialRegistry" in summary["classes"]
    assert "G4Material.hh" in summary["includes"]
    assert isinstance(summary["public_methods"], list)
    assert isinstance(summary["provided_symbols"], list)


def test_extract_file_summary_with_empty_content():
    """Empty content should return empty lists, not crash."""
    file_data = {
        "path": "include/Empty.hh",
        "new_content": "",
        "generated_by": "test_module_agent",
        "module_name": "test",
    }
    summary = _extract_file_summary("test", file_data)
    assert summary["classes"] == []
    assert summary["includes"] == []
    assert summary["public_methods"] == []
