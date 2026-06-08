from __future__ import annotations

from agent_core.g4_codegen.module_gates.geometry_hard_gate import run_geometry_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _geometry_source(content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path="src/DetectorConstruction.cc",
        operation="create_or_replace",
        new_content=content,
        generated_by="geometry_module_agent",
        module_name="geometry",
        rationale="test",
    )


def test_geometry_hard_gate_rejects_sensitive_detector_instantiation() -> None:
    result = run_geometry_hard_gate(
        [
            _geometry_source(
                '#include "DetectorConstruction.hh"\n'
                '#include "SensitiveDetector.hh"\n'
                "void DetectorConstruction::ConstructSDandField() {\n"
                '  auto* sd = new SensitiveDetector("SiliconSD");\n'
                "  fSiliconLogic->SetSensitiveDetector(sd);\n"
                "}\n"
            )
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("SensitiveDetector" in e for e in result.errors)
