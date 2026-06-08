"""P0-10: Hard gate rejects ModuleAgentResult with status='failed'."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.module_gates.material_hard_gate import run_material_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _valid_file() -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path="include/Test.hh",
        new_content="#pragma once\n",
        generated_by="test_module_agent",
        module_name="test",
        rationale="test",
    )


def test_failed_status_rejected():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="failed")
    assert result.status == "fail"
    assert any("module_status" in c["check"] for c in result.checks)


def test_generated_status_accepted():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="generated")
    assert result.status == "pass"


def test_repaired_status_accepted():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="repaired")
    assert result.status == "pass"


def test_unknown_status_rejected():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="unknown")
    assert result.status == "fail"


def test_none_status_not_checked():
    """When module_status is None, skip the check (backward compat)."""
    result = run_hard_gate_checks("test", [_valid_file()], module_status=None)
    assert result.status == "pass"


def test_module_hard_gate_wrapper_accepts_module_status():
    files = [
        GeneratedModuleFile(
            path="include/MaterialRegistry.hh",
            new_content=(
                "#pragma once\n"
                "#include \"G4Material.hh\"\n"
                "#include \"G4String.hh\"\n"
                "#include <map>\n"
                "class MaterialRegistry {\n"
                "public:\n"
                "  void AddCustomMaterial(const G4String& name, G4Material* material);\n"
                "  G4Material* GetMaterial(const G4String& name);\n"
                "private:\n"
                "  std::map<G4String, G4Material*> fMaterials;\n"
                "};\n"
            ),
            generated_by="material_module_agent",
            module_name="material",
            rationale="test",
        ),
        GeneratedModuleFile(
            path="src/MaterialRegistry.cc",
            new_content=(
                "#include \"MaterialRegistry.hh\"\n"
                "#include \"G4NistManager.hh\"\n"
                "#include <stdexcept>\n"
                "void MaterialRegistry::AddCustomMaterial(\n"
                "    const G4String& name, G4Material* material) {\n"
                "  if (!material) { throw std::runtime_error(\"missing material\"); }\n"
                "  fMaterials[name] = material;\n"
                "}\n"
                "G4Material* MaterialRegistry::GetMaterial(const G4String& name) {\n"
                "  auto it = fMaterials.find(name);\n"
                "  if (it != fMaterials.end()) { return it->second; }\n"
                "  auto* material = G4NistManager::Instance()->FindOrBuildMaterial(name);\n"
                "  if (!material) { throw std::runtime_error(\"material unavailable\"); }\n"
                "  fMaterials[name] = material;\n"
                "  return material;\n"
                "}\n"
            ),
            generated_by="material_module_agent",
            module_name="material",
            rationale="test",
        ),
    ]

    result = run_material_hard_gate(files, module_status="generated")

    assert result.status == "pass"
