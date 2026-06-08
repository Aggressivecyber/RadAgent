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


def _named_file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
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


def test_output_manager_hard_gate_requires_summary_and_metadata_interfaces() -> None:
    result = run_output_manager_hard_gate(
        [
            _named_file(
                "include/OutputManager.hh",
                "#ifndef OUTPUTMANAGER_HH\n#define OUTPUTMANAGER_HH\n"
                "class G4Run; class G4Event; class G4Step;\n"
                "class OutputManager { public:\n"
                "static OutputManager* Instance();\n"
                "void BeginRun(const G4Run*); void EndRun(const G4Run*);\n"
                "void BeginEvent(const G4Event*); void EndEvent(const G4Event*);\n"
                "void RecordStep(const G4Step*); void WriteEvent(const G4Event*);\n"
                "};\n#endif\n",
            ),
            _named_file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "OutputManager* OutputManager::Instance(){return nullptr;}\n"
                "void OutputManager::BeginRun(const G4Run*){}\n"
                "void OutputManager::EndRun(const G4Run*){}\n"
                "void OutputManager::BeginEvent(const G4Event*){}\n"
                "void OutputManager::EndEvent(const G4Event*){}\n"
                "void OutputManager::RecordStep(const G4Step*){}\n"
                "void OutputManager::WriteEvent(const G4Event*){}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("SetRunMetadata" in error for error in result.errors)
    assert any("WriteRunSummary" in error for error in result.errors)
    assert any("WriteMetadata" in error for error in result.errors)


def test_output_manager_hard_gate_rejects_missing_one_arg_write_event() -> None:
    result = run_output_manager_hard_gate(
        [
            _named_file(
                "include/OutputManager.hh",
                "#ifndef OUTPUTMANAGER_HH\n#define OUTPUTMANAGER_HH\n"
                "class G4Run; class G4Event; class G4Step;\n"
                "class OutputManager { public:\n"
                "static OutputManager* Instance();\n"
                "void BeginRun(const G4Run*); void EndRun(const G4Run*);\n"
                "void BeginEvent(const G4Event*); void EndEvent(const G4Event*);\n"
                "void RecordStep(const G4Step*);\n"
                "void WriteEvent(const G4Event*, double, double);\n"
                "void SetRunMetadata(const std::string&, const std::string&);\n"
                "void WriteRunSummary(); void WriteMetadata();\n"
                "};\n#endif\n",
            ),
            _named_file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "OutputManager* OutputManager::Instance(){return nullptr;}\n"
                "void OutputManager::BeginRun(const G4Run*){}\n"
                "void OutputManager::EndRun(const G4Run*){}\n"
                "void OutputManager::BeginEvent(const G4Event*){}\n"
                "void OutputManager::EndEvent(const G4Event*){}\n"
                "void OutputManager::RecordStep(const G4Step*){}\n"
                "void OutputManager::WriteEvent(const G4Event*, double, double){}\n"
                "void OutputManager::SetRunMetadata(const std::string&, const std::string&){}\n"
                "void OutputManager::WriteRunSummary(){}\n"
                "void OutputManager::WriteMetadata(){}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("WriteEvent(const G4Event* event)" in error for error in result.errors)


def test_output_manager_hard_gate_accepts_unnamed_one_arg_write_event() -> None:
    result = run_output_manager_hard_gate(
        [
            _named_file(
                "include/OutputManager.hh",
                "#ifndef OUTPUTMANAGER_HH\n#define OUTPUTMANAGER_HH\n"
                "class G4Run; class G4Event; class G4Step;\n"
                "class OutputManager { public:\n"
                "static OutputManager* Instance();\n"
                "void BeginRun(const G4Run*); void EndRun(const G4Run*);\n"
                "void BeginEvent(const G4Event*); void EndEvent(const G4Event*);\n"
                "void RecordStep(const G4Step*); void WriteEvent(const G4Event*);\n"
                "void SetRunMetadata(const std::string&, const std::string&);\n"
                "void WriteRunSummary(); void WriteMetadata();\n"
                "};\n#endif\n",
            ),
            _named_file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "OutputManager* OutputManager::Instance(){return nullptr;}\n"
                "void OutputManager::BeginRun(const G4Run*){}\n"
                "void OutputManager::EndRun(const G4Run*){}\n"
                "void OutputManager::BeginEvent(const G4Event*){}\n"
                "void OutputManager::EndEvent(const G4Event*){}\n"
                "void OutputManager::RecordStep(const G4Step*){}\n"
                "void OutputManager::WriteEvent(const G4Event*){}\n"
                "void OutputManager::SetRunMetadata(const std::string&, const std::string&){}\n"
                "void OutputManager::WriteRunSummary(){}\n"
                "void OutputManager::WriteMetadata(){}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "pass"


def test_output_manager_hard_gate_accepts_comment_only_one_arg_write_event() -> None:
    result = run_output_manager_hard_gate(
        [
            _named_file(
                "include/OutputManager.hh",
                "#ifndef OUTPUTMANAGER_HH\n#define OUTPUTMANAGER_HH\n"
                "class G4Run; class G4Event; class G4Step;\n"
                "class OutputManager { public:\n"
                "static OutputManager* Instance();\n"
                "void BeginRun(const G4Run*); void EndRun(const G4Run*);\n"
                "void BeginEvent(const G4Event*); void EndEvent(const G4Event*);\n"
                "void RecordStep(const G4Step*); void WriteEvent(const G4Event* /*event*/);\n"
                "void SetRunMetadata(const std::string&, const std::string&);\n"
                "void WriteRunSummary(); void WriteMetadata();\n"
                "};\n#endif\n",
            ),
            _named_file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "OutputManager* OutputManager::Instance(){return nullptr;}\n"
                "void OutputManager::BeginRun(const G4Run*){}\n"
                "void OutputManager::EndRun(const G4Run*){}\n"
                "void OutputManager::BeginEvent(const G4Event*){}\n"
                "void OutputManager::EndEvent(const G4Event*){}\n"
                "void OutputManager::RecordStep(const G4Step*){}\n"
                "void OutputManager::WriteEvent(const G4Event* /*event*/){}\n"
                "void OutputManager::SetRunMetadata(const std::string&, const std::string&){}\n"
                "void OutputManager::WriteRunSummary(){}\n"
                "void OutputManager::WriteMetadata(){}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "pass"
