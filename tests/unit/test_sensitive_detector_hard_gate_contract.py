from __future__ import annotations

from agent_core.g4_codegen.module_gates.sensitive_detector_hard_gate import (
    run_sensitive_detector_hard_gate,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="sensitive_detector_module_agent",
        module_name="sensitive_detector",
        rationale="test",
    )


def test_sensitive_detector_hard_gate_rejects_static_attach_and_hallucinated_name() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file(
                "include/Hit.hh",
                (
                    "#ifndef HIT_HH\n#define HIT_HH\n"
                    "class Hit { public: void SetEdep(double); };\n#endif\n"
                ),
            ),
            _file(
                "src/Hit.cc",
                '#include "Hit.hh"\n#include "G4UnitsTable.hh"\n'
                "void print() { std::setw(7); }\n",
            ),
            _file(
                "include/SensitiveDetector.hh",
                "#ifndef SENSITIVEDETECTOR_HH\n#define SENSITIVEDETECTOR_HH\n"
                "class SensitiveDetector { public: static void AttachTo(G4LogicalVolume* lv); };\n"
                "#endif\n",
            ),
            _file(
                "src/SensitiveDetector.cc",
                '#include "SensitiveDetector.hh"\n'
                "void SensitiveDetector::Initialize(G4HCofThisEvent*) {\n"
                '  auto* hc = new HitsCollection(SensitiveDetectorName, "hits");\n'
                "}\n"
                "G4bool SensitiveDetector::ProcessHits(G4Step* aStep, G4TouchableHistory*) {\n"
                "  auto* hit = new Hit();\n"
                "  return true;\n"
                "}\n"
                "void SensitiveDetector::AttachTo(G4LogicalVolume* lv) {\n"
                "  lv->SetSensitiveDetector(this);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("AttachTo must not be declared static" in e for e in result.errors)
    assert any("SensitiveDetectorName" in e for e in result.errors)
    assert any("SetTrackID" in e for e in result.errors)
    assert any("<iomanip>" in e for e in result.errors)


def test_sensitive_detector_hard_gate_requires_all_module_files() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file(
                "src/SensitiveDetector.cc",
                '#include "SensitiveDetector.hh"\n'
                "G4bool SensitiveDetector::ProcessHits(G4Step* aStep, G4TouchableHistory*) {\n"
                "  hit->SetTrackID(aStep->GetTrack()->GetTrackID());\n"
                "  return true;\n"
                "}\n",
            )
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("include/SensitiveDetector.hh" in e for e in result.errors)
    assert any("include/Hit.hh" in e for e in result.errors)


def test_sensitive_detector_hard_gate_rejects_unqualified_hit_allocation() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file("include/Hit.hh", "#pragma once\nclass Hit { public: void SetTrackID(int); };\n"),
            _file("src/Hit.cc", '#include "Hit.hh"\n'),
            _file("include/SensitiveDetector.hh", "#pragma once\nclass SensitiveDetector {};\n"),
            _file(
                "src/SensitiveDetector.cc",
                '#include "SensitiveDetector.hh"\n'
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  Hit* hit = new Hit();\n"
                "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
                "  return true;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("::Hit" in error for error in result.errors)


def test_sensitive_detector_hard_gate_rejects_unqualified_hit_collection_type() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file("include/Hit.hh", "#pragma once\nclass Hit { public: void SetTrackID(int); };\n"),
            _file("src/Hit.cc", '#include "Hit.hh"\n'),
            _file(
                "include/SensitiveDetector.hh",
                "#pragma once\n"
                '#include "G4THitsCollection.hh"\n'
                '#include "Hit.hh"\n'
                "class SensitiveDetector {\n"
                "  G4THitsCollection<Hit>* fHitsCollection;\n"
                "};\n",
            ),
            _file(
                "src/SensitiveDetector.cc",
                '#include "SensitiveDetector.hh"\n'
                '#include "G4THitsCollection.hh"\n'
                "void SensitiveDetector::Initialize(G4HCofThisEvent*) {\n"
                "  fHitsCollection = new G4THitsCollection<Hit>(GetName(), collectionName[0]);\n"
                "}\n"
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  ::Hit* hit = new ::Hit();\n"
                "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
                "  return true;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4THitsCollection<::Hit>" in error for error in result.errors)


def test_sensitive_detector_hard_gate_rejects_hits_collection_push_back() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file("include/Hit.hh", "#pragma once\nclass Hit { public: void SetTrackID(int); };\n"),
            _file("src/Hit.cc", '#include "Hit.hh"\n'),
            _file(
                "include/SensitiveDetector.hh",
                "#pragma once\n"
                '#include "G4THitsCollection.hh"\n'
                '#include "Hit.hh"\n'
                "class SensitiveDetector {\n"
                "  G4THitsCollection<::Hit>* fHitsCollection;\n"
                "};\n",
            ),
            _file(
                "src/SensitiveDetector.cc",
                '#include "SensitiveDetector.hh"\n'
                '#include "G4THitsCollection.hh"\n'
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  ::Hit* hit = new ::Hit();\n"
                "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
                "  fHitsCollection->push_back(hit);\n"
                "  return true;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("insert(hit)" in error for error in result.errors)


def test_sensitive_detector_hard_gate_rejects_inline_allocator_declarations() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file(
                "include/Hit.hh",
                "#pragma once\n"
                "class Hit {\n"
                "public:\n"
                "  inline void* operator new(size_t);\n"
                "  inline void operator delete(void*);\n"
                "  void SetTrackID(int);\n"
                "  int GetTrackID() const;\n"
                "};\n",
            ),
            _file("src/Hit.cc", '#include "Hit.hh"\n'),
            _file("include/SensitiveDetector.hh", "#pragma once\nclass SensitiveDetector {};\n"),
            _file(
                "src/SensitiveDetector.cc",
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  ::Hit* hit = new ::Hit();\n"
                "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
                "  return true;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("must not be inline" in error for error in result.errors)


def test_sensitive_detector_hard_gate_rejects_g4bestunit_header() -> None:
    result = run_sensitive_detector_hard_gate(
        [
            _file(
                "include/Hit.hh",
                "#pragma once\n"
                "class Hit { public: void SetTrackID(int); int GetTrackID() const; };\n",
            ),
            _file("src/Hit.cc", '#include "Hit.hh"\n#include "G4BestUnit.hh"\n'),
            _file("include/SensitiveDetector.hh", "#pragma once\nclass SensitiveDetector {};\n"),
            _file(
                "src/SensitiveDetector.cc",
                "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                "  ::Hit* hit = new ::Hit();\n"
                "  hit->SetTrackID(step->GetTrack()->GetTrackID());\n"
                "  return true;\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4UnitsTable.hh" in error for error in result.errors)
