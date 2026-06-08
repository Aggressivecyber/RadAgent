"""Sensitive detector module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult

REQUIRED_FILES = {
    "include/Hit.hh",
    "src/Hit.cc",
    "include/SensitiveDetector.hh",
    "src/SensitiveDetector.cc",
}


def run_sensitive_detector_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for sensitive detector module."""
    result = run_hard_gate_checks(
        module_name="sensitive_detector",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[
            "G4ParticleGun",
            r'#include\s+[<"]OutputManager\.hh[>"]',
            r"\bOutputManager\s*::",
            r"\bOutputManager\s*\*",
            r"\bOutputManager\s+",
        ],
    )

    checks = list(result.checks)
    errors = list(result.errors)
    warnings = list(result.warnings)

    files_by_path = {f.path: f for f in generated_files}
    for path in sorted(REQUIRED_FILES - set(files_by_path)):
        checks.append(
            {
                "check": "sensitive_detector_required_file",
                "status": "fail",
                "message": f"Missing mandatory sensitive detector file {path}",
            }
        )
        errors.append(f"Missing mandatory sensitive detector file {path}")

    header = files_by_path.get("include/SensitiveDetector.hh")
    source = files_by_path.get("src/SensitiveDetector.cc")
    hit_header = files_by_path.get("include/Hit.hh")
    hit_source = files_by_path.get("src/Hit.cc")

    if header:
        has_static_attach = bool(
            re.search(
                r"\bstatic\b[^;\n]*\bAttachTo\s*\(",
                header.new_content,
                re.MULTILINE,
            )
        )
        checks.append(
            {
                "check": "sensitive_detector_attachto_not_static",
                "status": "fail" if has_static_attach else "pass",
                "message": (
                    "AttachTo must not be declared static when it uses detector instance state"
                ),
            }
        )
        if has_static_attach:
            errors.append("SensitiveDetector::AttachTo must not be declared static")

        if "G4LogicalVolume" in header.new_content and not re.search(
            r"(class\s+G4LogicalVolume\s*;|#include\s+[<\"]G4LogicalVolume\.hh[>\"])",
            header.new_content,
        ):
            checks.append(
                {
                    "check": "sensitive_detector_logical_volume_declared",
                    "status": "fail",
                    "message": (
                        "SensitiveDetector.hh uses G4LogicalVolume but does not include or "
                        "forward declare it"
                    ),
                }
            )
            errors.append(
                "SensitiveDetector.hh uses G4LogicalVolume but does not include or "
                "forward declare it"
            )
        if re.search(r"\bG4THitsCollection\s*<\s*Hit\s*>", header.new_content):
            checks.append(
                {
                    "check": "sensitive_detector_hits_collection_qualified_hit_type",
                    "status": "fail",
                    "message": (
                        "Use G4THitsCollection<::Hit> in SensitiveDetector class scope; "
                        "unqualified Hit is hidden by G4VSensitiveDetector::Hit"
                    ),
                }
            )
            errors.append(
                "SensitiveDetector.hh must use G4THitsCollection<::Hit>, not "
                "G4THitsCollection<Hit>"
            )

    if source:
        if "SensitiveDetectorName" in source.new_content:
            checks.append(
                {
                    "check": "sensitive_detector_no_sensitive_detector_name_hallucination",
                    "status": "fail",
                    "message": "SensitiveDetectorName is not a valid G4VSensitiveDetector member",
                }
            )
            errors.append(
                "Replace hallucinated SensitiveDetectorName with SensitiveDetectorName-safe code"
            )

        if re.search(r"\bcollectionName\s*\.\s*insert\s*\(", source.new_content):
            checks.append(
                {
                    "check": "sensitive_detector_collection_name_push_back",
                    "status": "fail",
                    "message": (
                        "collectionName is a std::vector<G4String>; use push_back(), not insert()"
                    ),
                }
            )
            errors.append("SensitiveDetector.cc must use collectionName.push_back(...), not insert")

        if re.search(r"\bSetSensitiveDetector\s*\(\s*this\s*\)", source.new_content) and header:
            static_attach = bool(
                re.search(r"\bstatic\b[^;\n]*\bAttachTo\s*\(", header.new_content, re.MULTILINE)
            )
            checks.append(
                {
                    "check": "sensitive_detector_static_attach_no_this",
                    "status": "fail" if static_attach else "pass",
                    "message": "A static AttachTo method cannot use this",
                }
            )
            if static_attach:
                errors.append("Static SensitiveDetector::AttachTo uses this")

        if re.search(r"\bSetLogicalVolume\s*\(", source.new_content):
            checks.append(
                {
                    "check": "sensitive_detector_no_set_logical_volume",
                    "status": "fail",
                    "message": (
                        "G4VSensitiveDetector has no SetLogicalVolume API; use "
                        "G4LogicalVolume::SetSensitiveDetector(this)"
                    ),
                }
            )
            errors.append(
                "SensitiveDetector must not call SetLogicalVolume; use "
                "G4LogicalVolume::SetSensitiveDetector(this)"
            )

        process_hits = re.search(
            r"G4bool\s+SensitiveDetector::ProcessHits\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}",
            source.new_content,
            re.DOTALL,
        )
        body = process_hits.group("body") if process_hits else source.new_content
        has_track_id = "SetTrackID" in body and "GetTrackID" in body
        checks.append(
            {
                "check": "sensitive_detector_process_hits_sets_track_id",
                "status": "pass" if has_track_id else "fail",
                "message": "ProcessHits must store step->GetTrack()->GetTrackID() on each hit",
            }
        )
        if not has_track_id:
            errors.append("ProcessHits must call hit->SetTrackID(step->GetTrack()->GetTrackID())")
        unqualified_hit_allocation = bool(
            re.search(r"\bHit\s*\*\s+\w+\s*=\s*new\s+Hit\s*\(", body)
        )
        checks.append(
            {
                "check": "sensitive_detector_qualified_hit_allocation",
                "status": "fail" if unqualified_hit_allocation else "pass",
                "message": "Use ::Hit when allocating hits inside ProcessHits",
            }
        )
        if unqualified_hit_allocation:
            errors.append("ProcessHits must allocate hits as ::Hit to avoid name hiding")

        uses_hits_collection = bool(re.search(r"\bG4THitsCollection\s*<", source.new_content))
        has_hits_collection_include = bool(
            re.search(r"#include\s+[<\"]G4THitsCollection\.hh[>\"]", source.new_content)
        )
        checks.append(
            {
                "check": "sensitive_detector_hits_collection_include",
                "status": "pass"
                if not uses_hits_collection or has_hits_collection_include
                else "fail",
                "message": (
                    "SensitiveDetector.cc must include G4THitsCollection.hh when using "
                    "G4THitsCollection<Hit>"
                ),
            }
        )
        if uses_hits_collection and not has_hits_collection_include:
            errors.append(
                "SensitiveDetector.cc must include G4THitsCollection.hh when using "
                "G4THitsCollection<Hit>"
            )
        if re.search(r"\bG4THitsCollection\s*<\s*Hit\s*>", source.new_content):
            checks.append(
                {
                    "check": "sensitive_detector_source_qualified_hit_collection_type",
                    "status": "fail",
                    "message": (
                        "Use G4THitsCollection<::Hit> in SensitiveDetector methods; "
                        "unqualified Hit is hidden by G4VSensitiveDetector::Hit"
                    ),
                }
            )
            errors.append(
                "SensitiveDetector.cc must use G4THitsCollection<::Hit>, not "
                "G4THitsCollection<Hit>"
            )
        if re.search(r"\bfHitsCollection\s*->\s*push_back\s*\(", source.new_content):
            checks.append(
                {
                    "check": "sensitive_detector_hits_collection_insert_api",
                    "status": "fail",
                    "message": (
                        "G4THitsCollection does not have push_back(); use "
                        "fHitsCollection->insert(hit)"
                    ),
                }
            )
            errors.append(
                "SensitiveDetector.cc must use fHitsCollection->insert(hit), not push_back"
            )

    if hit_header:
        declares_track_id = (
            "SetTrackID" in hit_header.new_content and "GetTrackID" in hit_header.new_content
        )
        checks.append(
            {
                "check": "hit_declares_track_id_accessors",
                "status": "pass" if declares_track_id else "fail",
                "message": "Hit.hh must declare SetTrackID and GetTrackID accessors",
            }
        )
        if not declares_track_id:
            errors.append("Hit.hh must declare SetTrackID and GetTrackID")
        inline_allocator_decls = bool(
            re.search(
                r"\binline\s+void\s*\*\s*operator\s+new\s*\(\s*size_t\s*\)\s*;",
                hit_header.new_content,
            )
            or re.search(
                r"\binline\s+void\s+operator\s+delete\s*\(\s*void\s*\*\s*\)\s*;",
                hit_header.new_content,
            )
        )
        checks.append(
            {
                "check": "hit_allocator_not_inline_declaration_only",
                "status": "fail" if inline_allocator_decls else "pass",
                "message": (
                    "Hit.hh must not declare allocator operator new/delete as inline unless "
                    "the full definitions are also in the header"
                ),
            }
        )
        if inline_allocator_decls:
            errors.append(
                "Hit.hh allocator operator new/delete declarations must not be inline "
                "when definitions are in Hit.cc"
            )

    if hit_source:
        if "G4BestUnit.hh" in hit_source.new_content:
            checks.append(
                {
                    "check": "hit_no_g4bestunit_header",
                    "status": "fail",
                    "message": "Use G4UnitsTable.hh for G4BestUnit; G4BestUnit.hh does not exist",
                }
            )
            errors.append("Hit.cc must include G4UnitsTable.hh, not G4BestUnit.hh")

        uses_iomanip = bool(re.search(r"std::(setw|setprecision|fixed)\b", hit_source.new_content))
        has_iomanip = (
            '#include <iomanip>' in hit_source.new_content
            or '#include "iomanip"' in hit_source.new_content
        )
        checks.append(
            {
                "check": "hit_iomanip_include",
                "status": "pass" if not uses_iomanip or has_iomanip else "fail",
                "message": "Hit.cc must include <iomanip> when using std::setw/std::setprecision",
            }
        )
        if uses_iomanip and not has_iomanip:
            errors.append("Hit.cc must include <iomanip> when using std::setw/std::setprecision")
        uses_invalid_allocator_api = bool(
            re.search(r"\bG4Allocator\s*<", hit_source.new_content)
            and re.search(r"\.\s*(alloc|free)\s*\(", hit_source.new_content)
        )
        checks.append(
            {
                "check": "hit_allocator_uses_geant4_api",
                "status": "fail" if uses_invalid_allocator_api else "pass",
                "message": (
                    "G4Allocator uses MallocSingle()/FreeSingle(); it has no alloc/free methods"
                ),
            }
        )
        if uses_invalid_allocator_api:
            errors.append(
                "Hit.cc allocator operator new/delete must use MallocSingle()/FreeSingle(), "
                "not alloc/free"
            )

    for f in generated_files:
        if not f.path.endswith((".cc", ".hh")):
            continue
        uses_units = bool(
            re.search(
                r"\b(CLHEP::)?(MeV|keV|GeV|eV|ns|ms|s|mm|cm|m|um|nm|Gy)\b",
                f.new_content,
            )
        )
        has_units_include = bool(
            re.search(r"#include\s+[<\"]G4SystemOfUnits\.hh[>\"]", f.new_content)
        )
        checks.append(
            {
                "check": "sensitive_detector_units_include",
                "status": "pass" if not uses_units or has_units_include else "fail",
                "message": "Files that use Geant4/CLHEP units must include G4SystemOfUnits.hh",
            }
        )
        if uses_units and not has_units_include:
            errors.append(f"{f.path}: must include G4SystemOfUnits.hh when using units")

    return ModuleGateResult(
        module_name="sensitive_detector",
        gate_type="hard",
        status="fail" if errors else result.status,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )
