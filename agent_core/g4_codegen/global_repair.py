"""Global repair pass for assembled Geant4 module code.

This pass handles cross-module integration issues that individual module agents
cannot reliably fix in isolation: CMake source wiring, common compatibility
methods, and thin API adapters between generated classes.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


def run_global_code_repair(
    proposed_patch: dict[str, Any],
    job_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Repair the assembled proposed_patch and persist a structured report."""
    repaired_patch = deepcopy(proposed_patch or {})
    changed_files = repaired_patch.get("changed_files", [])
    report: dict[str, Any] = {
        "job_id": job_id,
        "status": "passed",
        "agent_name": "global_code_repair_agent",
        "issues_fixed": [],
        "changed_files": [],
        "errors": [],
    }

    if not isinstance(changed_files, list) or not changed_files:
        report["status"] = "failed"
        report["errors"].append("proposed_patch.changed_files is empty")
        _persist_report(report, job_id)
        return repaired_patch, report

    by_path = {f.get("path", ""): f for f in changed_files if isinstance(f, dict)}

    _repair_cmake_sources(by_path, report)
    _repair_material_registry(by_path, report)
    _repair_placement_manager(by_path, report)
    _repair_physics_factory(by_path, report)
    _repair_main_physics_constructor(by_path, report)
    _repair_main_detector_constructor(by_path, report)
    _repair_output_manager(by_path, report)
    _repair_scoring_manager(by_path, report)
    _repair_sensitive_detector(by_path, report)

    repaired_patch.setdefault("metadata", {})
    repaired_patch["metadata"]["global_code_repair"] = {
        "status": report["status"],
        "issues_fixed": len(report["issues_fixed"]),
        "report_path": "06_codegen/global_code_repair_report.json",
    }

    _persist_patch(repaired_patch, job_id)
    _persist_report(report, job_id)
    return repaired_patch, report


def _repair_cmake_sources(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    cmake_entry = by_path.get("CMakeLists.txt")
    if not cmake_entry:
        _error(report, "missing CMakeLists.txt for global CMake repair")
        return

    src_files = sorted(
        path for path in by_path if path.startswith("src/") and path.endswith(".cc")
    )
    if not src_files:
        _error(report, "no src/*.cc files available for CMake source list")
        return

    content = cmake_entry.get("new_content", "")
    original = content

    if "CMAKE_CXX_STANDARD" not in content:
        content = re.sub(
            r"(project\s*\([^\)]*\)\s*)",
            "\\1\nset(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)\n",
            content,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if content == original:
            content = (
                "set(CMAKE_CXX_STANDARD 17)\n"
                "set(CMAKE_CXX_STANDARD_REQUIRED ON)\n"
                + content
            )

    executable_match = re.search(r"add_executable\s*\(\s*([^\s\)]+)", content)
    target = executable_match.group(1) if executable_match else "RadAgentG4"
    explicit_sources = " ".join(["main.cc", *src_files])
    replacement = f"add_executable({target} {explicit_sources})"

    if re.search(r"add_executable\s*\([^\)]*\)", content, flags=re.DOTALL):
        content = re.sub(
            r"add_executable\s*\([^\)]*\)",
            replacement,
            content,
            count=1,
            flags=re.DOTALL,
        )
    else:
        content = content.rstrip() + f"\n{replacement}\n"

    if "target_include_directories" not in content:
        content += f"\ntarget_include_directories({target} PRIVATE include)\n"

    if content != original:
        cmake_entry["new_content"] = content
        _fixed(report, "CMakeLists.txt", "normalized C++ standard and executable sources")


def _repair_material_registry(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    header = by_path.get("include/MaterialRegistry.hh")
    source = by_path.get("src/MaterialRegistry.cc")
    if not header or not source:
        return

    header_content = header.get("new_content", "")
    original_header = header_content
    header_content = re.sub(
        r"\n\s*G4Material\*\s+GetMaterial\s*\(\s*const\s+std::string&\s+\w+\s*\)\s*;",
        "",
        header_content,
    )
    header_changed = header_content != original_header
    if "GetInstance(" not in header_content:
        header_content = _insert_declaration_text(
            header_content,
            "static MaterialRegistry& GetInstance();",
            "Initialize",
        )
        header_changed = True
    if header_changed:
        header["new_content"] = header_content

    source_content = source.get("new_content", "")
    original_source = source_content
    source_content = re.sub(
        r"\n\s*G4Material\*\s+MaterialRegistry::GetMaterial\s*\("
        r"\s*const\s+std::string&\s+\w+\s*\)\s*\{.*?\n\}",
        "",
        source_content,
        flags=re.DOTALL,
    )
    source_changed = source_content != original_source
    if "MaterialRegistry::GetInstance(" not in source_content:
        source_content = (
            source_content.rstrip()
            + "\n\nMaterialRegistry& MaterialRegistry::GetInstance() {\n"
            + "    static MaterialRegistry registry;\n"
            + "    return registry;\n"
            + "}\n"
        )
        source_changed = True
    if source_changed:
        source["new_content"] = source_content

    if header_changed or source_changed:
        _fixed(
            report,
            "MaterialRegistry",
            "normalized material registry overloads and singleton adapter",
        )


def _repair_placement_manager(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    header = by_path.get("include/PlacementManager.hh")
    source = by_path.get("src/PlacementManager.cc")
    if not header or not source:
        return

    place_decl = (
        "static G4VPhysicalVolume* Place(G4LogicalVolume* logical,\n"
        "                                  const G4ThreeVector& position,\n"
        "                                  G4RotationMatrix* rotation,\n"
        "                                  G4LogicalVolume* mother,\n"
        "                                  G4bool checkOverlaps = true);"
    )
    header_changed = False
    header_content = header.get("new_content", "")
    updated_header = re.sub(
        r"\bstatic\s+G4PVPlacement\*\s+Place\s*\(",
        "static G4VPhysicalVolume* Place(",
        header_content,
    )
    updated_header = re.sub(
        r"(\bPlaceVolume\s*\([^;]*?)G4VPhysicalVolume\s*\*\s*mother",
        r"\1G4LogicalVolume* mother",
        updated_header,
        flags=re.DOTALL,
    )
    updated_header = re.sub(
        r"^\s*class\s+G4RotationMatrix\s*;\s*\n?",
        "",
        updated_header,
        flags=re.MULTILINE,
    )
    if (
        "G4RotationMatrix" in updated_header
        and "G4RotationMatrix.hh" not in updated_header
    ):
        updated_header = _ensure_include_text(updated_header, "G4RotationMatrix.hh")
    if updated_header != header_content:
        header["new_content"] = updated_header
        header_changed = True
    if _ensure_forward_declaration(header, "G4VPhysicalVolume"):
        header_changed = True
    if not re.search(
        r"\bstatic\s+G4VPhysicalVolume\*\s+Place\s*\(\s*G4LogicalVolume\*\s+logical",
        header.get("new_content", ""),
    ):
        header_changed = _insert_before_private_or_class_end(header, place_decl)

    source_content = source.get("new_content", "")
    original_source = source_content
    source_content = re.sub(
        r"\bG4PVPlacement\*\s+PlacementManager::Place\s*\(",
        "G4VPhysicalVolume* PlacementManager::Place(",
        source_content,
    )
    source_content = re.sub(
        r"(\bPlacementManager::PlaceVolume\s*\([^)]*?)G4VPhysicalVolume\s*\*\s*mother",
        r"\1G4LogicalVolume* mother",
        source_content,
        flags=re.DOTALL,
    )
    source_content = re.sub(
        r"return\s+Instance\(\)->PlaceVolume\s*\(\s*"
        r"logical\s*,\s*logical->GetName\(\)\s*,\s*mother\s*,\s*position\s*,\s*"
        r"rotation\s*,\s*0\s*,\s*checkOverlaps\s*\)\s*;",
        (
            "static PlacementManager manager;\n"
            "    return manager.PlaceVolume(\n"
            "        rotation, position, logical, logical->GetName(), mother, false, 0,\n"
            "        checkOverlaps);"
        ),
        source_content,
    )
    if "void SetCheckOverlaps" in header.get("new_content", ""):
        source_content = re.sub(
            r"return\s+manager\.PlaceVolume\(\s*"
            r"rotation,\s*position,\s*logical,\s*logical->GetName\(\),\s*mother,\s*"
            r"false,\s*0,\s*checkOverlaps\s*\)\s*;",
            (
                "manager.SetCheckOverlaps(checkOverlaps);\n"
                "    return manager.PlaceVolume(\n"
                "        rotation, position, logical, logical->GetName(), mother, false, 0);"
            ),
            source_content,
        )
    source_content = re.sub(
        r"static\s+PlacementManager\s+manager;\s*\n\s*return\s+manager\.PlaceVolume"
        r"\(\s*rotation,\s*position,\s*logical,\s*logical->GetName\(\),\s*mother,\s*"
        r"false,\s*0,\s*checkOverlaps\s*\)\s*;",
        (
            "return PlacementManager::PlaceVolume(\n"
            "        rotation, position, logical, logical->GetName(), mother, false, 0,\n"
            "        checkOverlaps);"
        ),
        source_content,
    )
    source_changed = False
    if "PlacementManager::Place(" not in source_content:
        source["new_content"] = (
            source_content.rstrip()
            + "\n\nG4VPhysicalVolume* PlacementManager::Place(\n"
            + "    G4LogicalVolume* logical,\n"
            + "    const G4ThreeVector& position,\n"
            + "    G4RotationMatrix* rotation,\n"
            + "    G4LogicalVolume* mother,\n"
            + "    G4bool checkOverlaps) {\n"
            + "    return PlacementManager::PlaceVolume(\n"
            + "        rotation, position, logical, logical->GetName(), mother, false, 0,\n"
            + "        checkOverlaps);\n"
            + "}\n"
        )
        source_changed = True
    elif source_content != original_source:
        source["new_content"] = source_content
        source_changed = True

    if header_changed or source_changed:
        _fixed(report, "PlacementManager", "added static Place compatibility adapter")


def _repair_physics_factory(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    header = by_path.get("include/PhysicsListFactoryWrapper.hh")
    source = by_path.get("src/PhysicsListFactoryWrapper.cc")
    if not header or not source:
        return

    header_content = header.get("new_content", "")
    original_header = header_content
    header_content = re.sub(
        r"\s*static\s+G4VModularPhysicsList\s*\*\s*list\s*\(\s*\)\s*;\n?",
        "\n",
        header_content,
    )
    if header_content != original_header:
        header["new_content"] = header_content

    source_content = source.get("new_content", "")
    original_source = source_content
    source_content = re.sub(
        r"\bSetDefaultCutValue\s*\(\s*([^,\)]+(?:\([^)]*\))?[^,\)]*)\s*,\s*"
        r"['\"][^'\"]+['\"]\s*\)\s*;",
        r"SetDefaultCutValue(\1);",
        source_content,
    )
    cut_changed = source_content != original_source
    before_list_adapter = source_content
    source_content = re.sub(
        r"\n\s*G4VModularPhysicsList\s*\*\s*PhysicsListFactoryWrapper::list\s*"
        r"\(\s*\)\s*\{.*?\n\}\s*",
        "\n",
        source_content,
        flags=re.DOTALL,
    )
    list_adapter_changed = source_content != before_list_adapter
    if source_content != original_source:
        source["new_content"] = source_content

    if header_content != original_header or list_adapter_changed:
        _fixed(report, "PhysicsListFactoryWrapper", "removed invalid list adapter")
    if cut_changed:
        _fixed(report, "PhysicsListFactoryWrapper", "normalized SetDefaultCutValue usage")


def _repair_main_physics_constructor(
    by_path: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> None:
    main = by_path.get("main.cc")
    if not main:
        return

    content = main.get("new_content", "")
    updated = re.sub(
        r"new\s+PhysicsListFactoryWrapper\s*\(\s*\"[^\"]+\"\s*\)",
        "new PhysicsListFactoryWrapper()",
        content,
    )
    updated = re.sub(
        r"runManager->SetUserInitialization\s*\(\s*new\s+PhysicsListFactoryWrapper\s*"
        r"\(\s*\)\s*\)\s*;",
        (
            "auto* physicsWrapper = new PhysicsListFactoryWrapper();\n"
            "    runManager->SetUserInitialization(physicsWrapper->CreatePhysicsList());"
        ),
        updated,
    )
    wrapper_decl = re.search(
        r"(?:auto|PhysicsListFactoryWrapper)\s*\*?\s+([A-Za-z_]\w*)\s*=\s*"
        r"new\s+PhysicsListFactoryWrapper\s*\(\s*\)\s*;",
        updated,
    )
    if wrapper_decl:
        wrapper_name = wrapper_decl.group(1)
        updated = re.sub(
            rf"runManager->SetUserInitialization\s*\(\s*{re.escape(wrapper_name)}\s*\)\s*;",
            f"runManager->SetUserInitialization({wrapper_name}->CreatePhysicsList());",
            updated,
        )
    physics_changed = updated != content
    before_output_action = updated
    updated = re.sub(
        r"\n\s*runManager->SetUserAction\s*\(\s*static_cast\s*<\s*"
        r"G4User(?:Run|Event|Stepping)Action\s*\*>\s*\(\s*[A-Za-z_]\w*\s*\)\s*\)\s*;",
        "",
        updated,
    )
    if updated != content:
        main["new_content"] = updated
        if physics_changed:
            _fixed(report, "main.cc", "matched PhysicsListFactoryWrapper physics list creation")
        if before_output_action != updated:
            _fixed(report, "main.cc", "removed invalid OutputManager user action casts")


def _repair_main_detector_constructor(
    by_path: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> None:
    main = by_path.get("main.cc")
    detector_header = by_path.get("include/DetectorConstruction.hh")
    if not main or not detector_header:
        return

    detector_content = detector_header.get("new_content", "")
    if not re.search(r"\bDetectorConstruction\s*\(\s*MaterialRegistry\s*\*", detector_content):
        return

    content = main.get("new_content", "")
    original = content
    if "MaterialRegistry.hh" not in content:
        content = _ensure_include_text(content, "MaterialRegistry.hh")
    if "materialRegistry" not in content:
        with_registry = re.sub(
            r"(\bauto\*\s+runManager\s*=\s*G4RunManagerFactory::CreateRunManager\(\)\s*;\s*)",
            (
                "\\1\n"
                "    auto* materialRegistry = new MaterialRegistry();\n"
                "    materialRegistry->Initialize();\n"
            ),
            content,
            count=1,
        )
        if with_registry == content:
            with_registry = re.sub(
                r"(\brunManager->SetUserInitialization\s*\(\s*new\s+DetectorConstruction)",
                (
                    "auto* materialRegistry = new MaterialRegistry();\n"
                    "    materialRegistry->Initialize();\n\n"
                    "    \\1"
                ),
                content,
                count=1,
            )
        content = with_registry
    content = re.sub(
        r"new\s+DetectorConstruction\s*\(\s*\)",
        "new DetectorConstruction(materialRegistry)",
        content,
    )
    if content != original:
        main["new_content"] = content
        _fixed(report, "main.cc", "matched DetectorConstruction MaterialRegistry constructor")


def _repair_output_manager(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    header = by_path.get("include/OutputManager.hh")
    source = by_path.get("src/OutputManager.cc")
    if not header or not source:
        return

    header_content = header.get("new_content", "")
    original_header = header_content
    if "class G4Run;" not in header_content and "#include \"G4Run.hh\"" not in header_content:
        header_content = "class G4Run;\n" + header_content
    if "class G4Event;" not in header_content and "#include \"G4Event.hh\"" not in header_content:
        header_content = "class G4Event;\n" + header_content
    if "class G4Step;" not in header_content and "#include \"G4Step.hh\"" not in header_content:
        header_content = "class G4Step;\n" + header_content
    declarations = [
        (r"\bBeginRun\s*\(\s*const\s+G4Run\s*\*", "void BeginRun(const G4Run* run);", "Instance"),
        (r"\bEndRun\s*\(\s*const\s+G4Run\s*\*", "void EndRun(const G4Run* run);", "BeginRun"),
        (
            r"\bBeginEvent\s*\(\s*const\s+G4Event\s*\*",
            "void BeginEvent(const G4Event* event);",
            "EndRun",
        ),
        (
            r"\bEndEvent\s*\(\s*const\s+G4Event\s*\*",
            "void EndEvent(const G4Event* anEvent);",
            "BeginEvent",
        ),
        (
            r"\bRecordStep\s*\(\s*const\s+G4Step\s*\*",
            "void RecordStep(const G4Step* step);",
            "EndEvent",
        ),
        (
            r"\bWriteEvent\s*\(\s*const\s+G4Event\s*\*\s*(?:[A-Za-z_]\w*|/\*.*?\*/)?\s*\)\s*;",
            "void WriteEvent(const G4Event* anEvent);",
            "RecordStep",
        ),
    ]
    for marker_pattern, declaration, anchor in declarations:
        if not re.search(marker_pattern, header_content):
            header_content = _insert_declaration_text(header_content, declaration, anchor)
    if header_content != original_header:
        header["new_content"] = header_content

    source_content = source.get("new_content", "")
    source_changed = False
    additions: list[str] = []
    if "OutputManager::BeginRun(" not in source_content:
        if "OutputManager::BeginOfRun(" in source_content:
            additions.append(
                "void OutputManager::BeginRun(const G4Run*) {\n"
                "    BeginOfRun(\"radagent_g4\");\n"
                "}\n"
            )
        else:
            additions.append("void OutputManager::BeginRun(const G4Run*) {}\n")
    if "OutputManager::EndRun(" not in source_content:
        if "OutputManager::EndOfRun(" in source_content:
            additions.append(
                "void OutputManager::EndRun(const G4Run*) {\n"
                "    EndOfRun();\n"
                "}\n"
            )
        else:
            additions.append("void OutputManager::EndRun(const G4Run*) {}\n")
    if "OutputManager::BeginEvent(" not in source_content:
        additions.append("void OutputManager::BeginEvent(const G4Event*) {}\n")
    if "OutputManager::EndEvent(" not in source_content:
        additions.append("void OutputManager::EndEvent(const G4Event*) {}\n")
    if "OutputManager::RecordStep(" not in source_content:
        additions.append("void OutputManager::RecordStep(const G4Step*) {}\n")
    if not re.search(
        r"\bOutputManager::WriteEvent\s*\(\s*const\s+G4Event\s*\*\s*(?:[A-Za-z_]\w*|/\*.*?\*/)?"
        r"\s*\)",
        source_content,
    ):
        additions.append(
            "void OutputManager::WriteEvent(const G4Event* anEvent) {\n"
            "    EndEvent(anEvent);\n"
            "}\n"
        )
    if additions:
        source["new_content"] = source_content.rstrip() + "\n\n" + "\n".join(additions)
        source_changed = True

    if header_content != original_header or source_changed:
        _fixed(report, "OutputManager", "added action interface compatibility adapters")


def _repair_scoring_manager(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    source = by_path.get("src/ScoringManager.cc")
    if not source:
        return
    content = source.get("new_content", "")
    updated = re.sub(r"scMgr->GetMeshName\s*\(\s*iMesh\s*\)", '"scoringMesh"', content)
    updated = re.sub(
        r"(\b(?:scManager|scMgr|scoringManager)\s*->\s*GetMesh\s*)"
        r"\(\s*(?:fMeshName|meshName|\"[^\"]+\"|'[^']+')\s*\)",
        r"\1(0)",
        updated,
    )
    updated = re.sub(
        r"\bauto\s*&\s+([A-Za-z_]\w*)\s*=\s*([^;]*->\s*GetScoreMap\s*\(\s*\))\s*;",
        r"auto \1 = \2;",
        updated,
    )
    updated = re.sub(
        r"\bmesh\s*->\s*GetElementCenter\s*\(\s*copyNo\s*,\s*center\s*\)\s*;",
        (
            "const int nxRaw = static_cast<int>(fMeshNBins.x());\n"
            "        const int nyRaw = static_cast<int>(fMeshNBins.y());\n"
            "        const int nzRaw = static_cast<int>(fMeshNBins.z());\n"
            "        const int nx = nxRaw > 0 ? nxRaw : 1;\n"
            "        const int ny = nyRaw > 0 ? nyRaw : 1;\n"
            "        const int nz = nzRaw > 0 ? nzRaw : 1;\n"
            "        const int iz = copyNo / (nx * ny);\n"
            "        const int rem = copyNo % (nx * ny);\n"
            "        const int iy = rem / nx;\n"
            "        const int ix = rem % nx;\n"
            "        center = fMeshCenter + G4ThreeVector(\n"
            "            ((ix + 0.5) / nx - 0.5) * fMeshFullSize.x(),\n"
            "            ((iy + 0.5) / ny - 0.5) * fMeshFullSize.y(),\n"
            "            ((iz + 0.5) / nz - 0.5)\n"
            "                * fMeshFullSize.z());"
        ),
        updated,
    )
    if updated != content:
        source["new_content"] = updated
        _fixed(report, "ScoringManager", "normalized G4ScoringManager mesh access")


def _repair_sensitive_detector(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    changed = False
    for path in (
        "include/SensitiveDetector.hh",
        "src/SensitiveDetector.cc",
        "include/Hit.hh",
        "src/Hit.cc",
    ):
        entry = by_path.get(path)
        if not entry:
            continue
        content = entry.get("new_content", "")
        updated = re.sub(
            r"#include\s+[<\"]G4BestUnit\.hh[>\"]",
            '#include "G4UnitsTable.hh"',
            content,
        )
        updated = re.sub(r"\bG4THitsCollection\s*<\s*Hit\s*>", "G4THitsCollection<::Hit>", updated)
        updated = re.sub(
            r"\bHit\s*\*\s+hit\s*=\s*new\s+Hit\s*\(\s*\)\s*;",
            "::Hit* hit = new ::Hit();",
            updated,
        )
        updated = re.sub(
            r"\bfHitsCollection\s*->\s*push_back\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;",
            r"fHitsCollection->insert(\1);",
            updated,
        )
        updated = re.sub(
            r"\binline\s+(void\s*\*\s*operator\s+new\s*\(\s*size_t\s*\)\s*;)",
            r"\1",
            updated,
        )
        updated = re.sub(
            r"\binline\s+(void\s+operator\s+delete\s*\(\s*void\s*\*\s*\)\s*;)",
            r"\1",
            updated,
        )
        if updated != content:
            entry["new_content"] = updated
            changed = True
    if changed:
        _fixed(report, "SensitiveDetector", "qualified Hit collection and allocation types")


def _ensure_public_declaration(
    file_entry: dict[str, Any],
    declaration: str,
    anchor: str,
) -> bool:
    content = file_entry.get("new_content", "")
    if declaration in content:
        return False
    updated = _insert_declaration_text(content, declaration, anchor)
    if updated == content:
        updated = _insert_before_private_or_class_end_text(content, declaration)
    file_entry["new_content"] = updated
    return updated != content


def _ensure_forward_declaration(file_entry: dict[str, Any], class_name: str) -> bool:
    content = file_entry.get("new_content", "")
    declaration = f"class {class_name};"
    if (
        declaration in content
        or f'#include "{class_name}.hh"' in content
        or f"#include <{class_name}.hh>" in content
    ):
        return False
    lines = content.splitlines()
    insert_at = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#include") or stripped.startswith("#define"):
            insert_at = idx + 1
    lines.insert(insert_at, declaration)
    file_entry["new_content"] = "\n".join(lines) + "\n"
    return True


def _ensure_include_text(content: str, header_name: str) -> str:
    quoted = f'#include "{header_name}"'
    angled = f"#include <{header_name}>"
    if quoted in content or angled in content:
        return content
    lines = content.splitlines()
    insert_at = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#pragma once") or stripped.startswith("#include"):
            insert_at = idx + 1
    lines.insert(insert_at, quoted)
    return "\n".join(lines) + "\n"


def _insert_declaration_text(content: str, declaration: str, anchor: str) -> str:
    if declaration in content:
        return content
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if anchor in line and ";" in line:
            indent = re.match(r"\s*", line).group(0)
            lines.insert(idx + 1, f"{indent}{declaration}")
            return "\n".join(lines) + "\n"
    return _insert_before_private_or_class_end_text(content, declaration)


def _insert_before_private_or_class_end(file_entry: dict[str, Any], declaration: str) -> bool:
    content = file_entry.get("new_content", "")
    updated = _insert_before_private_or_class_end_text(content, declaration)
    file_entry["new_content"] = updated
    return updated != content


def _insert_before_private_or_class_end_text(content: str, declaration: str) -> str:
    if declaration in content:
        return content
    if "private:" in content:
        return content.replace("private:", f"    {declaration}\nprivate:", 1)
    return re.sub(r"\n};\s*$", f"\n    {declaration}\n}};\n", content, count=1)


def _fixed(report: dict[str, Any], path_or_symbol: str, message: str) -> None:
    report["issues_fixed"].append({"target": path_or_symbol, "message": message})
    if path_or_symbol not in report["changed_files"]:
        report["changed_files"].append(path_or_symbol)


def _error(report: dict[str, Any], message: str) -> None:
    report["status"] = "failed"
    report["errors"].append(message)


def _persist_patch(patch: dict[str, Any], job_id: str) -> None:
    from agent_core.config.workspace import get_job_dir

    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "proposed_patch.json").write_text(
        json.dumps(patch, indent=2, ensure_ascii=False)
    )


def _persist_report(report: dict[str, Any], job_id: str) -> None:
    from agent_core.config.workspace import get_job_dir

    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "global_code_repair_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
