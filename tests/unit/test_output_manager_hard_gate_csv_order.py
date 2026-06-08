from __future__ import annotations

from agent_core.g4_codegen.module_gates.output_manager_hard_gate import (
    run_output_manager_hard_gate,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path="src/OutputManager.cc",
        operation="create_or_replace",
        new_content=content,
        generated_by="output_manager_module_agent",
        module_name="output_manager",
        rationale="test",
    )


def test_output_manager_hard_gate_rejects_quantity_map_csv_iteration() -> None:
    result = run_output_manager_hard_gate(
        [
            _file(
                '#include "OutputManager.hh"\n'
                "void OutputManager::RecordEventData(\n"
                "    int eventID, const std::map<std::string, double>& quantities) {\n"
                "  csvFile << eventID;\n"
                "  for (const auto& kv : quantities) {\n"
                "    csvFile << \",\" << kv.second;\n"
                "  }\n"
                "}\n"
            )
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("RecordEventData must not write fixed CSV columns" in e for e in result.errors)


def test_output_manager_hard_gate_allows_header_ordered_lookup() -> None:
    result = run_output_manager_hard_gate(
        [
            _file(
                '#include "OutputManager.hh"\n'
                "void OutputManager::RecordEventData(\n"
                "    int eventID, const std::map<std::string, double>& quantities) {\n"
                "  const auto edep = quantities.find(\"edep_MeV\");\n"
                "  const auto dose = quantities.find(\"dose_Gy\");\n"
                "  csvFile << eventID << \",\";\n"
                "  csvFile << (edep == quantities.end() ? 0.0 : edep->second) << \",\";\n"
                "  csvFile << (dose == quantities.end() ? 0.0 : dose->second) << \"\\n\";\n"
                "}\n"
            )
        ],
        module_status="generated",
    )

    assert result.status == "pass"
