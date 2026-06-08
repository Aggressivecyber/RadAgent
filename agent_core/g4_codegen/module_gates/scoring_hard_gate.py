"""Scoring module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_scoring_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for scoring module."""
    result = run_hard_gate_checks(
        module_name="scoring",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=["G4ParticleGun", "G4PVPlacement", "G4Box", "G4NistManager"],
    )
    checks = list(result.checks)
    errors = list(result.errors)

    paths = {f.path for f in generated_files}
    for required in ("include/ScoringManager.hh", "src/ScoringManager.cc"):
        if required not in paths:
            checks.append(
                {
                    "check": "scoring_required_file",
                    "status": "fail",
                    "message": f"Missing mandatory scoring file {required}",
                }
            )
            errors.append(f"Missing mandatory scoring file {required}")

    for f in generated_files:
        content = f.new_content
        if re.search(r"\bnew\s+G4ScoringManager\s*\(", content):
            checks.append(
                {
                    "check": "scoring_manager_singleton_api",
                    "status": "fail",
                    "message": (
                        "Use G4ScoringManager::GetScoringManager(); "
                        "do not allocate G4ScoringManager with new"
                    ),
                }
            )
            errors.append(f"{f.path}: use G4ScoringManager::GetScoringManager()")

        if f.path.endswith((".hh", ".h")) and "G4String" in content:
            has_g4string_include = bool(
                re.search(r"#include\s+[<\"]G4String\.hh[>\"]", content)
            )
            checks.append(
                {
                    "check": "scoring_g4string_header_include",
                    "status": "pass" if has_g4string_include else "fail",
                    "message": "Scoring headers that use G4String must include G4String.hh",
                }
            )
            if not has_g4string_include:
                errors.append(f"{f.path}: must include G4String.hh when declaring G4String")

        if f.path.endswith((".cc", ".hh")) and "CellFlux" in content:
            uses_cell_flux_class = "G4PSCellFlux" in content
            uses_dose_as_cell_flux = bool(
                re.search(
                    r"G4PSDoseDeposit\s*\*\s*\w*cell\w*\s*=\s*new\s+G4PSDoseDeposit",
                    content,
                    re.IGNORECASE,
                )
            )
            status = "pass" if uses_cell_flux_class and not uses_dose_as_cell_flux else "fail"
            checks.append(
                {
                    "check": "scoring_cell_flux_uses_cell_flux_scorer",
                    "status": status,
                    "message": "CellFlux scoring must use G4PSCellFlux, not G4PSDoseDeposit",
                }
            )
            if status == "fail":
                errors.append(f"{f.path}: CellFlux scoring must use G4PSCellFlux")

        file_output_patterns = [
            r'#include\s+"OutputManager\.hh"',
            r"\bOutputManager\s*::",
            r"\bstd\s*::\s*ofstream\b",
            r"\bofstream\b",
            r"\bfopen\s*\(",
            r"\bWrite[A-Za-z0-9_]*\s*\(",
            r"\bSave[A-Za-z0-9_]*\s*\(",
            r"\bGetScoringJSON\s*\(",
            r"\bstd\s*::\s*ostringstream\s+\w*json\w*",
            r'"[^"]*\.(csv|json)"',
            r"\boutput_file\b",
        ]
        if any(re.search(pattern, content, re.IGNORECASE) for pattern in file_output_patterns):
            checks.append(
                {
                    "check": "scoring_no_file_output",
                    "status": "fail",
                    "message": (
                        "ScoringManager must not write files or call OutputManager; "
                        "output_manager owns serialization/output"
                    ),
                }
            )
            errors.append(f"{f.path}: ScoringManager must not write files")

        hits_map_vars = re.findall(
            r"\bG4THitsMap\s*<[^>]+>\s*\*?\s*([A-Za-z_]\w*)\b",
            content,
        )
        direct_hits_map_find = any(
            re.search(rf"\b{re.escape(var)}\s*(?:->|\.)\s*find\s*\(", content)
            for var in hits_map_vars
        )
        if direct_hits_map_find:
            checks.append(
                {
                    "check": "scoring_g4thitsmap_access_api",
                    "status": "fail",
                    "message": (
                        "Use (*hits_map)[copyNo] or hits_map->GetMap()->find(copyNo); "
                        "do not call find() directly on G4THitsMap"
                    ),
                }
            )
            errors.append(f"{f.path}: invalid direct G4THitsMap find() access")

        invalid_mesh_access_patterns = [
            (
                r"\bGetScorer\s*\(",
                "G4VScoringMesh does not expose GetScorer(); use GetScoreMap()",
            ),
            (
                r"dynamic_cast\s*<\s*G4THitsMap\s*<[^>]+>\s*\*\s*>\s*\(",
                "Do not dynamic_cast primitive scorers to G4THitsMap; use GetScoreMap()",
            ),
            (
                r"\bG4VScorer\b",
                "Do not use hallucinated G4VScorer; use G4VScoringMesh::GetScoreMap()",
            ),
            (
                r"\bGetHitsMap\s*\(",
                "Do not read scoring mesh results through GetHitsMap(); use GetScoreMap()",
            ),
            (
                r"\bGetMeshName\s*\(",
                "G4ScoringManager has no GetMeshName(i); store the configured mesh name",
            ),
            (
                r"\bGetMesh\s*\(\s*(?!\d+\s*\))[^)]*\)",
                "G4ScoringManager::GetMesh requires an integer mesh index; use GetMesh(0)",
            ),
        ]
        for pattern, message in invalid_mesh_access_patterns:
            if re.search(pattern, content, re.DOTALL):
                checks.append(
                    {
                        "check": "scoring_mesh_result_access_api",
                        "status": "fail",
                        "message": message,
                    }
                )
                errors.append(f"{f.path}: {message}")

        if "GetScoreMap()" in content and "G4StatDouble" not in content:
            checks.append(
                {
                    "check": "scoring_score_map_value_type",
                    "status": "fail",
                    "message": (
                        "GetScoreMap() values are G4THitsMap<G4StatDouble>*; "
                        "include/use G4StatDouble"
                    ),
                }
            )
            errors.append(
                f"{f.path}: GetScoreMap() values require G4StatDouble and sum_wx() extraction"
            )

    return ModuleGateResult(
        module_name="scoring",
        gate_type="hard",
        status="fail" if errors else result.status,
        checks=checks,
        errors=errors,
        warnings=list(result.warnings),
    )
