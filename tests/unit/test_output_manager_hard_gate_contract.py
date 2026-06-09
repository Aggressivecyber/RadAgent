from __future__ import annotations

from agent_core.g4_codegen.module_gates.output_manager_hard_gate import (
    run_output_manager_hard_gate,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="output_manager_module_agent",
        module_name="output_manager",
        rationale="test",
    )


def _header() -> str:
    return (
        "#pragma once\n"
        '#include "G4String.hh"\n'
        "class G4Run;\n"
        "class G4Event;\n"
        "class G4Step;\n"
        "class OutputManager {\n"
        "public:\n"
        "  static OutputManager* Instance();\n"
        "  void BeginRun(const G4Run* run);\n"
        "  void EndRun(const G4Run* run);\n"
        "  void BeginEvent(const G4Event* event);\n"
        "  void EndEvent(const G4Event* event);\n"
        "  void RecordStep(const G4Step* step);\n"
        "  void WriteEvent(const G4Event* event);\n"
        "  void RecordEventData(const std::map<G4String, double>& data);\n"
        "  void SetRunMetadata(const G4String& key, const G4String& value);\n"
        "  void WriteRunSummary();\n"
        "  void WriteMetadata();\n"
        "};\n"
    )


def test_output_manager_hard_gate_rejects_job_prefixed_runtime_artifacts() -> None:
    result = run_output_manager_hard_gate(
        [
            _file("include/OutputManager.hh", _header()),
            _file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "#include <cstdlib>\n"
                "OutputManager* OutputManager::Instance() { return nullptr; }\n"
                "void OutputManager::BeginRun(const G4Run*) {}\n"
                "void OutputManager::EndRun(const G4Run*) { WriteRunSummary(); WriteMetadata(); }\n"
                "void OutputManager::BeginEvent(const G4Event*) {}\n"
                "void OutputManager::EndEvent(const G4Event*) {}\n"
                "void OutputManager::RecordStep(const G4Step*) {}\n"
                "void OutputManager::WriteEvent(const G4Event*) {\n"
                "  auto* dir = std::getenv(\"G4_OUTPUT_DIR\");\n"
                "  csv << \"EventID,edep_MeV,dose_Gy\";\n"
                "  std::ofstream f(std::string(dir) + \"/job0_events.csv\");\n"
                "}\n"
                "void OutputManager::RecordEventData(const std::map<G4String, double>&) {}\n"
                "void OutputManager::SetRunMetadata(const G4String&, const G4String&) {}\n"
                "void OutputManager::WriteRunSummary() {\n"
                "  std::ofstream f(\"job0_run_summary.json\");\n"
                "}\n"
                "void OutputManager::WriteMetadata() {\n"
                "  std::ofstream f(\"job0_metadata.json\");\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("job-prefixed" in error for error in result.errors)
    assert any("output.csv" in error for error in result.errors)


def test_output_manager_hard_gate_accepts_fixed_runtime_artifact_contract() -> None:
    result = run_output_manager_hard_gate(
        [
            _file("include/OutputManager.hh", _header()),
            _file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "#include <cstdlib>\n"
                "OutputManager* OutputManager::Instance() { return nullptr; }\n"
                "void OutputManager::BeginRun(const G4Run*) {}\n"
                "void OutputManager::EndRun(const G4Run*) { WriteRunSummary(); WriteMetadata(); }\n"
                "void OutputManager::BeginEvent(const G4Event*) {}\n"
                "void OutputManager::EndEvent(const G4Event*) {}\n"
                "void OutputManager::RecordStep(const G4Step*) {}\n"
                "void OutputManager::WriteEvent(const G4Event*) {\n"
                "  auto* dir = std::getenv(\"G4_OUTPUT_DIR\");\n"
                "  std::ofstream f(std::string(dir ? dir : \".\") + \"/output.csv\");\n"
                "  f << \"EventID,edep_MeV,dose_Gy\\n\";\n"
                "}\n"
                "void OutputManager::RecordEventData(const std::map<G4String, double>&) {}\n"
                "void OutputManager::SetRunMetadata(const G4String&, const G4String&) {}\n"
                "void OutputManager::WriteRunSummary() {\n"
                "  std::ofstream f(\"run_summary.json\");\n"
                "  f << \"{\\\"total_events\\\":0,\\\"total_edep_MeV\\\":0}\";\n"
                "}\n"
                "void OutputManager::WriteMetadata() {\n"
                "  std::ofstream f(\"metadata.json\");\n"
                "  f << \"{\\\"job_id\\\":\\\"test\\\"}\";\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "pass"


def test_output_manager_hard_gate_rejects_event_user_information_bridge() -> None:
    result = run_output_manager_hard_gate(
        [
            _file(
                "include/OutputManager.hh",
                _header()
                + '#include "G4VUserEventInformation.hh"\n'
                + "struct EventData : public G4VUserEventInformation {};\n",
            ),
            _file(
                "src/OutputManager.cc",
                '#include "OutputManager.hh"\n'
                "#include <cstdlib>\n"
                "OutputManager* OutputManager::Instance() { return nullptr; }\n"
                "void OutputManager::BeginRun(const G4Run*) {}\n"
                "void OutputManager::EndRun(const G4Run*) { WriteRunSummary(); WriteMetadata(); }\n"
                "void OutputManager::BeginEvent(const G4Event*) {}\n"
                "void OutputManager::EndEvent(const G4Event*) {}\n"
                "void OutputManager::RecordStep(const G4Step*) {}\n"
                "void OutputManager::WriteEvent(const G4Event* event) {\n"
                "  auto* data = event->GetUserInformation();\n"
                "  auto* dir = std::getenv(\"G4_OUTPUT_DIR\");\n"
                "  std::ofstream f(std::string(dir ? dir : \".\") + \"/output.csv\");\n"
                "  f << \"EventID,edep_MeV,dose_Gy\\n\";\n"
                "}\n"
                "void OutputManager::RecordEventData(const std::map<G4String, double>&) {}\n"
                "void OutputManager::SetRunMetadata(const G4String&, const G4String&) {}\n"
                "void OutputManager::WriteRunSummary() { std::ofstream f(\"run_summary.json\"); }\n"
                "void OutputManager::WriteMetadata() { std::ofstream f(\"metadata.json\"); }\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("EventData" in error for error in result.errors)
    assert any("G4VUserEventInformation" in error for error in result.errors)
