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

    if hit_source:
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
