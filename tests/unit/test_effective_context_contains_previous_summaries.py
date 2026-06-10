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
        "generated_by": "simulation_core_module_agent",
        "module_name": "simulation_core",
    }
    summary = _extract_file_summary("simulation_core", file_data)

    assert summary["module_name"] == "simulation_core"
    assert summary["path"] == "include/MaterialRegistry.hh"
    assert summary["generated_by"] == "simulation_core_module_agent"
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


def test_extract_file_summary_lists_all_public_methods():
    file_data = {
        "path": "include/OutputManager.hh",
        "new_content": (
            "#pragma once\n"
            "class OutputManager {\n"
            "public:\n"
            "  static OutputManager* Instance();\n"
            "  void BeginRun(const G4Run* run);\n"
            "  void EndRun(const G4Run* run);\n"
            "  void BeginEvent(const G4Event* event);\n"
            "  void EndEvent(const G4Event* event);\n"
            "  void RecordStep(const G4Step* step);\n"
            "  void WriteEvent(const G4Event* event);\n"
            "private:\n"
            "  int count_ = 0;\n"
            "};\n"
        ),
        "generated_by": "runtime_app_module_agent",
        "module_name": "runtime_app",
    }

    summary = _extract_file_summary("runtime_app", file_data)
    methods = set(summary["public_methods"])

    assert {
        "Instance",
        "BeginRun",
        "EndRun",
        "BeginEvent",
        "EndEvent",
        "RecordStep",
        "WriteEvent",
    }.issubset(methods)
