from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.global_repair import run_global_code_repair
from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers


def _file(path: str, content: str, module_name: str) -> dict[str, Any]:
    return {
        "path": path,
        "operation": "create_or_replace",
        "new_content": content,
        "zone": "green",
        "generated_by": f"{module_name}_module_agent",
        "module_name": module_name,
        "rationale": "unit test",
    }


def test_global_repair_promotes_common_magic_numbers_to_named_constants(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            _file(
                "include/ScoringManager.hh",
                """#pragma once
#include "G4Types.hh"
#include <array>

class ScoringManager {
public:
    void SetMeshParameters(
        const G4double center[3],
        const G4double halfSize[3],
        const G4int nBins[3]);
private:
    std::array<G4double, 3> fCenter;
    std::array<G4double, 3> fHalfSize;
    std::array<G4int, 3> fNBins;
};
""",
                "scoring",
            ),
            _file(
                "src/ScoringManager.cc",
"""#include "ScoringManager.hh"
#include <cstdio>

void ScoringManager::SetMeshParameters(
    const G4double center[3],
    const G4double halfSize[3],
    const G4int nBins[3]) {
    for (int i = 0; i < 3; ++i) {
        fCenter[i] = center[i];
    }
    char sizeCmd[256];
    char binCmd[256];
    G4double binWidth[3];
}
""",
                "scoring",
            ),
            _file(
                "src/OutputManager.cc",
                """#include "OutputManager.hh"
#include <sys/stat.h>
#include <iomanip>

namespace {
const char* kEnvOutputDir = "G4_OUTPUT_DIR";
}

OutputManager::OutputManager() {
    const char* envDir = std::getenv(kEnvOutputDir);
}
void OutputManager::EnsureOutputDirectory() {
    mkdir(fOutputDir.c_str(), 0755);
}
void OutputManager::WriteEvent() {
    fCsvFile << std::fixed << std::setprecision(6) << fEventEdep;
}
""",
                "output_manager",
            ),
            _file(
                "src/PrimaryGeneratorAction.cc",
                """#include "PrimaryGeneratorAction.hh"

void PrimaryGeneratorAction::GeneratePrimaries() {
    fParticleGun->SetParticleMomentumDirection(G4ThreeVector(0., 0., 1.));
}
""",
                "source",
            ),
            _file(
                "src/DetectorConstruction.cc",
                """#include "DetectorConstruction.hh"

G4VPhysicalVolume* DetectorConstruction::Construct() {
    new G4PVPlacement(0, G4ThreeVector(0.,0.,0.), targetLogical, "Target", worldLogical, false, 0);
    new G4PVPlacement(
        0, G4ThreeVector(0., 0., kPhantomOffsetZ),
        phantomLogical, "Phantom", worldLogical, false, 0);
    return worldPhysical;
}
""",
                "geometry",
            ),
            _file(
                "CMakeLists.txt",
                "project(RadAgentG4)\nadd_executable(RadAgentG4 main.cc)\n",
                "main_cmake",
            ),
        ]
    }

    repaired, report = run_global_code_repair(patch, "no_magic_global_repair")

    assert report["status"] == "passed"
    assert any(
        issue["target"] == "G4-G No Magic Number"
        for issue in report["issues_fixed"]
    )
    files = {entry["path"]: entry["new_content"] for entry in repaired["changed_files"]}
    assert 'std::getenv("G4_OUTPUT_DIR")' in files["src/OutputManager.cc"]
    assert "std::getenv(kEnvOutputDir)" not in files["src/OutputManager.cc"]
    for path in (
        "include/ScoringManager.hh",
        "src/ScoringManager.cc",
        "src/OutputManager.cc",
        "src/PrimaryGeneratorAction.cc",
        "src/DetectorConstruction.cc",
    ):
        clean, violations = check_magic_numbers(files[path], path)
        assert clean, violations
