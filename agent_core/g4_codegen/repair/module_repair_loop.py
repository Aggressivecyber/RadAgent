"""Module repair loop — attempts to fix failed modules."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_codegen.module_agents.base import (
    _extract_generated_file_entries,
    _normalize_generated_path,
)
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult, ModuleGateResult
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 3

REPAIR_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 模块修复 Agent。

当前模块的代码生成失败了。请根据以下信息修复代码：
1. 原始模块上下文
2. 失败的代码
3. 必须满足的生成约束
4. 当前代码和门禁检查摘要

要求：
1. 只修复当前模块的文件
2. 不要重新生成整个工程
3. 修复后的代码必须通过硬门禁
4. 必须输出纯 JSON 对象，不得输出 Markdown、解释文字或代码围栏
5. JSON 顶层必须包含 generated_files 数组
6. generated_files 中每个对象必须包含：
   path、operation、new_content、generated_by、module_name、rationale
7. 如果只修改部分文件，可以只返回修改文件；系统会按 path 合并未修改文件
8. 每个文件对象的路径字段固定为 path
9. 每个文件对象的完整文件内容字段固定为 new_content
10. JSON 顶层必须包含 generated_files 数组
11. generated_files 数组必须包含完整可写入文件，不是文件摘要、计划或说明

输出格式：
{
  "module_name": "<module_name>",
  "status": "repaired",
  "generated_files": [
    {
      "path": "include/Example.hh",
      "operation": "create_or_replace",
      "new_content": "...完整文件内容...",
      "generated_by": "<module_name>_module_agent",
      "module_name": "<module_name>",
      "rationale": "修复原因"
    }
  ],
  "errors": [],
  "warnings": []
}
"""


async def repair_module(
    module_name: str,
    module_context: dict[str, Any],
    original_result: ModuleAgentResult,
    gate_result: ModuleGateResult,
    job_id: str | None = None,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> ModuleAgentResult:
    """Attempt to repair a failed module.

    Up to max_attempts repair iterations.
    Each iteration:
    1. Send failure info to repair agent
    2. Get repaired code
    3. Re-run hard gate
    4. If pass, return repaired result
    """
    from agent_core.observability import record_event

    attempts: list[dict[str, Any]] = []
    current_result = original_result

    for attempt in range(max_attempts):
        logger.info("Repair attempt %d/%d for %s", attempt + 1, max_attempts, module_name)
        record_event(
            job_id=job_id,
            event_type="module_repair_attempt_start",
            status="running",
            phase="g4_codegen",
            module_name=module_name,
            summary=f"{module_name} repair attempt {attempt + 1}/{max_attempts}",
            metrics={"attempt": attempt + 1, "max_attempts": max_attempts},
            errors=list(gate_result.errors),
            warnings=list(gate_result.warnings),
        )

        # Build repair context
        repair_context = {
            "module_name": module_name,
            "module_context": module_context,
            "current_generated_files": [
                file_entry.model_dump() for file_entry in current_result.generated_files
            ],
            "implementation_requirements": _module_repair_requirements(module_name),
            "gate_requirements": _format_gate_requirements(module_name, gate_result),
            "attempt": attempt + 1,
            "max_attempts": max_attempts,
        }

        # Call repair agent
        gateway = get_model_gateway()
        result = await gateway.call(
            task=ModelTask.FAILURE_DIAGNOSIS,
            tier=ModelTier.MAX,
            system_prompt=REPAIR_SYSTEM_PROMPT,
            user_prompt=(
                "请修复下面的模块代码，并严格按 system prompt 中的 JSON schema 返回：\n"
                f"{json.dumps(repair_context, indent=2, ensure_ascii=False)[:30000]}"
            ),
            response_format="json",
            max_tokens=65536,
            metadata={
                "module_name": module_name,
                "job_id": job_id,
                "repair_attempt": attempt + 1,
            },
        )

        if result.error:
            record_event(
                job_id=job_id,
                event_type="module_repair_attempt_result",
                status="failed",
                phase="g4_codegen",
                module_name=module_name,
                summary=f"{module_name} repair call failed on attempt {attempt + 1}",
                metrics={"attempt": attempt + 1},
                errors=[result.error],
            )
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": f"Repair call failed: {result.error}",
                }
            )
            continue

        # Parse repair result
        try:
            data = result.parsed_json or json.loads(result.content.strip())
        except (json.JSONDecodeError, TypeError) as exc:
            record_event(
                job_id=job_id,
                event_type="module_repair_attempt_result",
                status="failed",
                phase="g4_codegen",
                module_name=module_name,
                summary=f"{module_name} repair returned invalid JSON on attempt {attempt + 1}",
                metrics={"attempt": attempt + 1},
                errors=[f"Invalid JSON: {exc}"],
            )
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": f"Invalid JSON: {exc}",
                }
            )
            continue

        # Build repaired result
        repaired_files: list[GeneratedModuleFile] = []
        for f in _extract_generated_file_entries(data):
            try:
                if not isinstance(f, dict):
                    raise TypeError(f"file entry must be object, got {type(f).__name__}")
                new_content = f.get("new_content", f.get("content"))
                if new_content is None:
                    raise KeyError("new_content")
                path = f.get(
                    "path",
                    f.get("file_path", f.get("filepath", f.get("filename", f.get("name")))),
                )
                if path is None:
                    raise KeyError("path")
                path = _normalize_generated_path(module_name, path)
                repaired_files.append(
                    GeneratedModuleFile(
                        path=path,
                        operation=f.get("operation", "create_or_replace"),
                        new_content=new_content,
                        generated_by=f.get("generated_by", f"{module_name}_module_agent"),
                        module_name=f.get("module_name", module_name),
                        rationale=f.get("rationale", "repaired"),
                        dependencies=f.get("dependencies", []),
                        satisfies=f.get("satisfies", []),
                        risk_notes=f.get("risk_notes", []),
                        used_references=f.get("used_references", []),
                    )
                )
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping invalid repair file entry for %s: %s", module_name, exc)

        if not repaired_files:
            record_event(
                job_id=job_id,
                event_type="module_repair_attempt_result",
                status="failed",
                phase="g4_codegen",
                module_name=module_name,
                summary=f"{module_name} repair returned no valid files on attempt {attempt + 1}",
                metrics={"attempt": attempt + 1},
                errors=["No valid files in repair response"],
            )
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": "No valid files in repair response",
                }
            )
            continue

        merged_files_by_path = {f.path: f for f in current_result.generated_files}
        for f in repaired_files:
            merged_files_by_path[f.path] = f
        if module_name == "main_cmake":
            for macro_name in ("run.mac", "init.mac"):
                macro_path = f"macros/{macro_name}"
                if macro_path in merged_files_by_path:
                    merged_files_by_path.pop(macro_name, None)
        _prune_files_outside_module_contract(module_name, module_context, merged_files_by_path)
        merged_files = list(merged_files_by_path.values())

        repaired_result = ModuleAgentResult(
            module_name=module_name,
            status="repaired",
            generated_files=merged_files,
            repair_attempts=attempts,
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )

        # Re-run the same module-specific hard gate used by the graph node.
        # The generic base gate is not enough for module boundary checks such
        # as scoring-vs-output ownership.
        from agent_core.g4_codegen.graph_nodes import _get_hard_gate_function

        gate = _get_hard_gate_function(module_name)(merged_files, module_status="repaired")
        record_event(
            job_id=job_id,
            event_type="module_repair_attempt_result",
            status="passed" if gate.status == "pass" else "failed",
            phase="g4_codegen",
            module_name=module_name,
            summary=f"{module_name} repair hard gate {gate.status} on attempt {attempt + 1}",
            metrics={
                "attempt": attempt + 1,
                "repaired_file_count": len(repaired_files),
                "generated_file_count": len(merged_files),
                "hard_gate_error_count": len(gate.errors),
            },
            errors=list(gate.errors),
            warnings=list(gate.warnings),
        )
        attempts.append(
            {
                "attempt": attempt + 1,
                "status": "repaired",
                "gate_status": gate.status,
                "repaired_file_count": len(repaired_files),
                "generated_file_count": len(merged_files),
            }
        )

        if gate.status == "pass":
            logger.info("Module %s repaired successfully on attempt %d", module_name, attempt + 1)
            repaired_result.repair_attempts = attempts
            return repaired_result

        current_result = repaired_result
        gate_result = gate

    # All attempts failed
    logger.warning("Module %s repair failed after %d attempts", module_name, max_attempts)
    return ModuleAgentResult(
        module_name=module_name,
        status="failed",
        generated_files=current_result.generated_files,
        repair_attempts=attempts,
        errors=[f"Repair failed after {max_attempts} attempts"] + current_result.errors,
    )


def save_repair_summary(
    module_name: str,
    result: ModuleAgentResult,
    job_id: str,
) -> None:
    """Save repair summary to disk."""
    from agent_core.config.workspace import get_job_dir

    repair_dir = get_job_dir(job_id) / "06_codegen" / "repair"
    repair_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "module_name": module_name,
        "status": result.status,
        "repair_attempts": result.repair_attempts,
        "errors": result.errors,
    }

    path = repair_dir / f"{module_name}_repair_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def _prune_files_outside_module_contract(
    module_name: str,
    module_context: dict[str, Any],
    merged_files_by_path: dict[str, GeneratedModuleFile],
) -> None:
    """Keep repaired module output inside the module contract file scope."""
    contract = module_context.get("module_contract")
    if not isinstance(contract, dict):
        return
    output_files = contract.get("output_files")
    if not isinstance(output_files, list) or not output_files:
        return

    allowed_paths = {
        _normalize_generated_path(module_name, path)
        for path in output_files
        if isinstance(path, str) and path.strip()
    }
    if not allowed_paths:
        return

    for path in list(merged_files_by_path):
        if path not in allowed_paths:
            merged_files_by_path.pop(path, None)


def _format_gate_requirements(
    module_name: str,
    gate_result: ModuleGateResult,
) -> list[str]:
    """Convert gate feedback into prescriptive requirements for the repair agent."""
    requirements: list[str] = []
    for message in [*gate_result.errors, *gate_result.warnings]:
        if not isinstance(message, str) or not message.strip():
            continue
        text = message.strip()
        if _is_contradicted_by_module_requirements(module_name, text):
            continue
        if ": " in text:
            text = text.split(": ", 1)[1]
        requirements.append(f"Make the repaired code satisfy this requirement: {text}")
    return requirements


def _is_contradicted_by_module_requirements(module_name: str, text: str) -> bool:
    """Filter LLM feedback that conflicts with hard module API facts."""
    lowered = text.lower()
    if module_name == "sensitive_detector":
        contradicted_phrases = (
            "redundant collectionname",
            "g4vsensitivedetector already adds",
            "remove the 'collectionname.push_back",
            "remove collectionname.push_back",
        )
        return any(phrase in lowered for phrase in contradicted_phrases)

    if module_name != "scoring":
        return False

    contradicted_phrases = (
        "getscoremap() method",
        "getscoremap() call",
        "getscoremap method",
        "getscoremap is non-existent",
        "non-existent g4vscoringmesh::getscoremap",
        "replace getscoremap",
        "use of g4vscoringmesh::getscoremap",
        "proper use of g4vscoringmesh::gethitsmap",
        "typically g4thitsmap<g4double>",
    )
    return any(phrase in lowered for phrase in contradicted_phrases)


def _module_repair_requirements(module_name: str) -> list[str]:
    """Return module-specific repair guidance phrased as implementation requirements."""
    if module_name == "scoring":
        return [
            "Use G4VScoringMesh::GetScoreMap() to read command-based scoring mesh results.",
            (
                "GetScoreMap() values are already G4THitsMap<G4StatDouble>*; assign "
                "scoreIt->second directly to G4THitsMap<G4StatDouble>*."
            ),
            (
                "Use scoreMap.find(\"edepScorer\") and scoreMap.find(\"doseScorer\") "
                "only on the score map."
            ),
            "Do not use dynamic_cast for scoring mesh result maps.",
            "Do not call find() directly on a G4THitsMap object.",
            (
                "To read a cell value, use hitsMap->GetObject(copyNo) and then "
                "G4StatDouble::sum_wx(), or use hitsMap->GetMap()->find(copyNo)."
            ),
            (
                "Use G4ScoringManager::GetScoringManager() to obtain the scoring manager "
                "singleton; do not allocate G4ScoringManager with new."
            ),
        ]
    if module_name == "sensitive_detector":
        return [
            (
                "Register hits collections with collectionName.push_back(...), "
                "not collectionName.insert(...)."
            ),
            (
                "Do not remove collectionName.push_back(...); Geant4 requires the "
                "concrete sensitive detector to register its hits collection names."
            ),
            (
                "Include G4THitsCollection.hh in SensitiveDetector.cc when using "
                "G4THitsCollection<Hit>."
            ),
            (
                "Do not call SetLogicalVolume; if AttachTo exists, attach with "
                "G4LogicalVolume::SetSensitiveDetector(this)."
            ),
            (
                "Include G4SystemOfUnits.hh in every Hit/SensitiveDetector file "
                "that uses Geant4 or CLHEP units."
            ),
            (
                "ProcessHits must store the track id with "
                "hit->SetTrackID(step->GetTrack()->GetTrackID())."
            ),
        ]
    if module_name == "placement":
        return [
            (
                "Use G4RotationMatrix* for G4PVPlacement rotation arguments, "
                "not const G4RotationMatrix*."
            ),
            (
                "When accepting const G4Transform3D&, create a non-const local copy before "
                "passing it to G4PVPlacement."
            ),
            "Keep placement code limited to PlacementManager.hh and PlacementManager.cc.",
        ]
    if module_name == "physics":
        return [
            (
                "Create the reference physics list with "
                "G4PhysListFactory::GetReferencePhysList and pass ownership to Geant4."
            ),
            (
                "Do not delete fPhysicsList; make the destructor defaulted or give it "
                "an empty function body."
            ),
            (
                "Do not write the exact text 'delete fPhysicsList' in generated code or "
                "comments."
            ),
            (
                "Keep the G4PhysListFactory object as a member or another long-lived "
                "object; do not return a list created from a local factory variable."
            ),
        ]
    if module_name == "output_manager":
        return [
            (
                "OutputManager.hh and OutputManager.cc must provide the stable "
                "action-facing methods BeginRun(const G4Run*), EndRun(const G4Run*), "
                "BeginEvent(const G4Event*), EndEvent(const G4Event*), "
                "RecordStep(const G4Step*), and WriteEvent(const G4Event*)."
            ),
            (
                "RecordStep(const G4Step*) is required by this project contract; keep it "
                "as an OutputManager method and implement it without querying ScoringManager "
                "or changing geometry, source, or physics state."
            ),
            (
                "WriteEvent must include a one-argument overload exactly compatible with "
                "action code: void WriteEvent(const G4Event* event). It may delegate to "
                "an overload that accepts edep_MeV and dose_Gy."
            ),
            (
                "Keep CSV/JSON writing in OutputManager only, and keep ScoringManager out "
                "of OutputManager includes and calls."
            ),
        ]
    if module_name == "material":
        return [
            (
                "Implement MaterialRegistry::Initialize or DefineAllMaterials so it "
                "actually registers IR materials with FindOrBuildMaterial and the custom "
                "material API."
            ),
            (
                "Do not use placeholder, dummy, stub, TODO, NotImplemented, 'for now', "
                "or 'should handle' in code or comments."
            ),
            (
                "When a material cannot be found, throw a concrete exception or return "
                "through an explicit failure path; do not silently skip registration."
            ),
            (
                "Expose only one GetMaterial string overload, preferably "
                "GetMaterial(const G4String&), to avoid string literal ambiguity."
            ),
        ]
    if module_name == "main_cmake":
        return [
            (
                "CMakeLists.txt must list the root entry file as main.cc, not src/main.cc."
            ),
            (
                "CMakeLists.txt must explicitly list every generated src/*.cc file from "
                "existing_generated_file_summaries."
            ),
            "Do not use file(GLOB) in CMake code or comments.",
            (
                "Keep generated macros under macros/run.mac and macros/init.mac; do not "
                "return root-level run.mac or init.mac."
            ),
            (
                "Instantiate PhysicsListFactoryWrapper using the constructor declared in "
                "the generated physics header."
            ),
            (
                "Pass physicsWrapper->CreatePhysicsList() to "
                "runManager->SetUserInitialization(...); do not pass the wrapper object."
            ),
            (
                "If macros/init.mac contains /run/initialize, main.cc must not call "
                "runManager->Initialize()."
            ),
        ]
    return []
