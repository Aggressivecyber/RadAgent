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
    _repair_output_manager(by_path, report)

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

    decl = "G4Material* GetMaterial(const std::string& name);"
    header_changed = _ensure_public_declaration(header, decl, "FindOrBuildMaterial")

    source_content = source.get("new_content", "")
    source_changed = False
    if "MaterialRegistry::GetMaterial(" not in source_content:
        source["new_content"] = (
            source_content.rstrip()
            + "\n\nG4Material* MaterialRegistry::GetMaterial(const std::string& name) {\n"
            + "    return FindOrBuildMaterial(name);\n"
            + "}\n"
        )
        source_changed = True

    if header_changed or source_changed:
        _fixed(report, "MaterialRegistry", "added GetMaterial compatibility adapter")


def _repair_placement_manager(by_path: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    header = by_path.get("include/PlacementManager.hh")
    source = by_path.get("src/PlacementManager.cc")
    if not header or not source:
        return

    place_decl = (
        "static G4PVPlacement* Place(G4LogicalVolume* logical,\n"
        "                                const G4ThreeVector& position,\n"
        "                                G4RotationMatrix* rotation,\n"
        "                                G4LogicalVolume* mother,\n"
        "                                G4bool checkOverlaps = true);"
    )
    header_changed = False
    if " Place(" not in header.get("new_content", ""):
        header_changed = _insert_before_private_or_class_end(header, place_decl)

    source_content = source.get("new_content", "")
    source_changed = False
    if "PlacementManager::Place(" not in source_content:
        source["new_content"] = (
            source_content.rstrip()
            + "\n\nG4PVPlacement* PlacementManager::Place(\n"
            + "    G4LogicalVolume* logical,\n"
            + "    const G4ThreeVector& position,\n"
            + "    G4RotationMatrix* rotation,\n"
            + "    G4LogicalVolume* mother,\n"
            + "    G4bool checkOverlaps) {\n"
            + "    return Instance()->PlaceVolume(\n"
            + "        logical, logical->GetName(), mother, position, rotation, 0,\n"
            + "        checkOverlaps);\n"
            + "}\n"
        )
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
    if '#include "G4VModularPhysicsList.hh"' not in header_content:
        header_content = header_content.replace(
            "class G4VModularPhysicsList;",
            '#include "G4VModularPhysicsList.hh"',
        )
    if "static G4VModularPhysicsList* list();" not in header_content:
        header_content = _insert_declaration_text(
            header_content,
            "static G4VModularPhysicsList* list();",
            "CreatePhysicsList",
        )
    if header_content != original_header:
        header["new_content"] = header_content

    source_content = source.get("new_content", "")
    source_changed = False
    if "PhysicsListFactoryWrapper::list(" not in source_content:
        source["new_content"] = (
            source_content.rstrip()
            + "\n\nG4VModularPhysicsList* PhysicsListFactoryWrapper::list() {\n"
            + "    return CreatePhysicsList();\n"
            + "}\n"
        )
        source_changed = True

    if header_content != original_header or source_changed:
        _fixed(report, "PhysicsListFactoryWrapper", "added list compatibility adapter")


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
        ("BeginRun(", "void BeginRun(const G4Run* run);", "Instance"),
        ("EndRun(", "void EndRun(const G4Run* run);", "BeginRun"),
        ("BeginEvent(", "void BeginEvent(const G4Event* event);", "EndRun"),
        ("EndEvent(", "void EndEvent(const G4Event* anEvent);", "BeginEvent"),
        ("RecordStep(", "void RecordStep(const G4Step* step);", "EndEvent"),
        ("WriteEvent(", "void WriteEvent(const G4Event* anEvent);", "RecordStep"),
    ]
    for marker, declaration, anchor in declarations:
        if marker not in header_content:
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
    if "OutputManager::WriteEvent(" not in source_content:
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
