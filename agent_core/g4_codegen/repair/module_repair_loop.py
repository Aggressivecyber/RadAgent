"""Module repair loop — attempts to fix failed modules."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_codegen.module_agents.base import (
    _extract_generated_file_entries,
    _normalize_generated_path,
    _normalize_string_list,
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
12. 如果 repair_context.module_context.runtime_failure_context 非空，必须把其中
    gate、build、ctest、smoke simulation、artifact contract 报告当作当前修复约束；
    只输出满足这些约束的新代码，不要复述旧失败过程。
13. 必须阅读 repair_context.retrieval_context 中的 RAG 和 web 证据；
    使用其中 API 事实时必须写入 generated_files[].used_references。
    used_references 必须是字符串数组，例如
    ["Geant4 Application Developers Guide: G4THitsCollection"]；
    不得返回对象、字典或嵌套数组。
14. 如果 RAG/web 证据与硬门禁要求冲突，以硬门禁要求为准；不得使用无证据的 Geant4 API。
15. 必须通过 G4-G No Magic Number gate：除 0、1、2、0.0、1.0、2.0、0.5、
    180、360 和带 CLHEP 单位的数值外，所有数字必须先定义为具名 const/constexpr/enum。
    数组维度、buffer size、setprecision、文件权限、坐标方向、循环上界不得直接写数字。
16. 修复方式示例：std::array<T, kAxisCount>，char buf[kCommandBufferSize]，
    std::setprecision(kCsvPrecision)，mkdir(path, kOutputDirectoryMode)，
    G4ThreeVector(0.0, 0.0, 1.0)；不要写 G4ThreeVector(0., 0., 1.)。
17. 只允许返回当前模块契约里的 owned/output files。不要新增 module_dependency.json、
    metadata.json、notes.txt 或任何契约外文件。依赖关系必须写入每个
    generated_files[].dependencies 字段，不得通过新增文件表达。

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
      "rationale": "修复原因",
      "used_references": ["Geant4 Application Developers Guide: relevant API"]
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
    resolved_job_id = job_id or module_context.get("job_id")

    for attempt in range(max_attempts):
        logger.info("Repair attempt %d/%d for %s", attempt + 1, max_attempts, module_name)
        record_event(
            job_id=resolved_job_id,
            event_type="module_repair_attempt_start",
            status="running",
            phase="g4_codegen",
            module_name=module_name,
            summary=f"{module_name} repair attempt {attempt + 1}/{max_attempts}",
            metrics={"attempt": attempt + 1, "max_attempts": max_attempts},
            errors=list(gate_result.errors),
            warnings=list(gate_result.warnings),
        )

        evidence_context = await _collect_repair_evidence(
            module_name=module_name,
            gate_result=gate_result,
            module_context=module_context,
            current_result=current_result,
            job_id=resolved_job_id,
            attempt=attempt + 1,
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
            "retrieval_context": evidence_context,
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
                "job_id": resolved_job_id,
                "repair_attempt": attempt + 1,
            },
        )

        if result.error:
            record_event(
                job_id=resolved_job_id,
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
                job_id=resolved_job_id,
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
                        dependencies=_normalize_string_list(f.get("dependencies", [])),
                        satisfies=_normalize_string_list(f.get("satisfies", [])),
                        risk_notes=_normalize_string_list(f.get("risk_notes", [])),
                        used_references=_normalize_string_list(f.get("used_references", [])),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping invalid repair file entry for %s: %s", module_name, exc)

        if not repaired_files:
            record_event(
                job_id=resolved_job_id,
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
        _postprocess_repaired_module_files(module_name, module_context, merged_files)

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
            job_id=resolved_job_id,
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


def _postprocess_repaired_module_files(
    module_name: str,
    module_context: dict[str, Any],
    generated_files: list[GeneratedModuleFile],
) -> None:
    _merge_contract_dependencies(module_context, generated_files)
    if module_name != "output_manager":
        return
    for file_entry in generated_files:
        if file_entry.path != "src/OutputManager.cc":
            continue
        file_entry.new_content = _normalize_output_manager_getenv_literals(
            file_entry.new_content
        )


def _merge_contract_dependencies(
    module_context: dict[str, Any],
    generated_files: list[GeneratedModuleFile],
) -> None:
    contract = module_context.get("module_contract")
    if not isinstance(contract, dict):
        return
    dependencies = contract.get("dependencies")
    if not isinstance(dependencies, list):
        return
    required_dependencies = [
        dependency
        for dependency in dependencies
        if isinstance(dependency, str) and dependency.strip()
    ]
    if not required_dependencies:
        return
    for file_entry in generated_files:
        existing = list(file_entry.dependencies or [])
        for dependency in required_dependencies:
            if dependency not in existing:
                existing.append(dependency)
        file_entry.dependencies = existing


def _normalize_output_manager_getenv_literals(content: str) -> str:
    import re

    env_var_names = {
        match.group(1)
        for match in re.finditer(
            r"(?:const\s+)?char\s*\*\s*(\w+)\s*=\s*\"G4_OUTPUT_DIR\"\s*;",
            content,
        )
    }
    env_var_names.update(
        match.group(1)
        for match in re.finditer(
            r"(?:const\s+)?std::string\s+(\w+)\s*=\s*\"G4_OUTPUT_DIR\"\s*;",
            content,
        )
    )
    updated = content
    for name in sorted(env_var_names):
        updated = re.sub(
            rf"\b(std::)?getenv\s*\(\s*{re.escape(name)}\s*\)",
            lambda match: f'{match.group(1) or ""}getenv("G4_OUTPUT_DIR")',
            updated,
        )
    return updated


async def _collect_repair_evidence(
    *,
    module_name: str,
    gate_result: ModuleGateResult,
    module_context: dict[str, Any],
    current_result: ModuleAgentResult,
    job_id: str | None,
    attempt: int,
) -> dict[str, Any]:
    """Retrieve RAG and web evidence for a concrete repair failure."""
    query = _build_repair_evidence_query(module_name, gate_result, current_result)
    evidence: dict[str, Any] = {
        "query": query,
        "rag": {"status": "not_run", "results": [], "errors": []},
        "web": {"status": "not_run", "results": [], "errors": []},
        "policy": {
            "required_for_real_repair": bool(job_id),
            "use": (
                "Use these RAG/web entries as API evidence and repair constraints. "
                "If evidence conflicts with module hard gates, the hard gate wins."
            ),
        },
    }

    # Unit tests often call repair_module without a job id; avoid unexpected
    # external services there. Real graph/module tests provide a job id.
    if not job_id:
        evidence["rag"]["status"] = "skipped_no_job_id"
        evidence["web"]["status"] = "skipped_no_job_id"
        return evidence

    try:
        rag_results = await _search_repair_rag(query)
        evidence["rag"] = {
            "status": "pass" if rag_results else "empty",
            "results": rag_results,
            "errors": [],
        }
    except Exception as exc:
        evidence["rag"] = {"status": "error", "results": [], "errors": [str(exc)]}

    try:
        web_results = await _search_repair_web(query)
        evidence["web"] = {
            "status": "pass" if web_results else "empty",
            "results": web_results,
            "errors": [],
        }
    except Exception as exc:
        evidence["web"] = {"status": "error", "results": [], "errors": [str(exc)]}

    _persist_repair_evidence(job_id, module_name, attempt, evidence)

    # Keep prompt payload bounded while still useful.
    evidence["rag"]["results"] = evidence["rag"]["results"][:5]
    evidence["web"]["results"] = evidence["web"]["results"][:5]
    return evidence


def _build_repair_evidence_query(
    module_name: str,
    gate_result: ModuleGateResult,
    current_result: ModuleAgentResult,
) -> str:
    """Build a focused Geant4 API query from concrete gate failures."""
    messages = [*gate_result.errors, *gate_result.warnings, *current_result.errors]
    filtered = [
        msg.strip()
        for msg in messages
        if isinstance(msg, str) and msg.strip()
    ][:8]
    module_requirements = _module_repair_requirements(module_name)[:4]
    return " ".join(
        [
            "Geant4",
            module_name,
            "repair",
            *filtered,
            *module_requirements,
        ]
    )[:1200]


async def _search_repair_rag(query: str) -> list[dict[str, Any]]:
    """Search local Geant4 RAG docs for repair evidence."""
    from agent_core.context.nodes import _ensure_indexed, _get_rag_client

    client = _get_rag_client()
    if not await client.backend_available():
        return []
    if not await _ensure_indexed(client):
        return []
    results = await client.search(query, top_k=6, min_score=0.25)
    return [
        {
            "doc_id": result.doc_id,
            "title": result.title,
            "content": result.content[:1200],
            "source": result.source,
            "score": round(result.score, 4),
        }
        for result in results
    ]


async def _search_repair_web(query: str) -> list[dict[str, Any]]:
    """Search web for repair evidence using the configured web tool."""
    from agent_core.tools.web_search_tool import WebSearchTool

    tool = WebSearchTool()
    if not tool.search_available:
        return []
    results = await tool.search(query, max_results=5)
    return [
        {
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet[:800],
            "source_type": result.source_type,
            "confidence": result.confidence,
        }
        for result in results
    ]


def _persist_repair_evidence(
    job_id: str,
    module_name: str,
    attempt: int,
    evidence: dict[str, Any],
) -> None:
    from agent_core.config.workspace import get_job_dir

    repair_dir = get_job_dir(job_id) / "06_codegen" / "repair"
    repair_dir.mkdir(parents=True, exist_ok=True)
    path = repair_dir / f"{module_name}_repair_evidence_attempt_{attempt}.json"
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")


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
    allowed_paths = _allowed_repair_paths(module_name, module_context)
    if not allowed_paths:
        return

    for path in list(merged_files_by_path):
        if path not in allowed_paths:
            merged_files_by_path.pop(path, None)


def _allowed_repair_paths(
    module_name: str,
    module_context: dict[str, Any],
) -> set[str]:
    paths: list[str] = []
    contract = module_context.get("module_contract")
    if isinstance(contract, dict):
        output_files = contract.get("output_files")
        if isinstance(output_files, list):
            paths.extend(path for path in output_files if isinstance(path, str))
    example = module_context.get("module_code_example")
    if isinstance(example, dict):
        owned_files = example.get("owned_files")
        if isinstance(owned_files, list):
            paths.extend(path for path in owned_files if isinstance(path, str))
    return {
        _normalize_generated_path(module_name, path)
        for path in paths
        if isinstance(path, str) and path.strip()
    }


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
    if module_name == "physics":
        return [
            (
                "physics_list.mac must contain only real Geant4 macro commands or "
                "necessary comments; do not include PLACEHOLDER, TODO, stub, dummy, "
                "NotImplemented, or sample-only text."
            ),
            (
                "Use C++ SetCuts()/SetCutValue or valid /run/setCut and "
                "/run/setCutForAGivenParticle macro commands for production cuts."
            ),
            (
                "Create the reference physics list with G4PhysListFactory and keep "
                "factory lifetime valid; do not return a physics list from a local "
                "temporary factory."
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
            (
                "Use G4Allocator<Hit>::MallocSingle() in operator new and "
                "G4Allocator<Hit>::FreeSingle(static_cast<Hit*>(ptr)) in operator "
                "delete; do not call nonexistent alloc/free methods."
            ),
            "Use G4UnitsTable.hh for G4BestUnit; do not include G4BestUnit.hh.",
        ]
    if module_name == "placement":
        return [
            (
                "Use G4RotationMatrix* for G4PVPlacement rotation arguments, "
                "not const G4RotationMatrix*."
            ),
            (
                "If PlacementManager.hh mentions G4RotationMatrix*, include "
                "G4RotationMatrix.hh; do not forward declare class G4RotationMatrix "
                "because Geant4 defines it as an alias."
            ),
            (
                "When accepting const G4Transform3D&, create a non-const local copy before "
                "passing it to G4PVPlacement."
            ),
            (
                "If PlaceVolume is static, static Place must call "
                "PlacementManager::PlaceVolume(...) directly; do not create a "
                "PlacementManager instance."
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
                "Do not write dose_Gy as a hard-coded 0.0 in event rows. Provide an explicit "
                "dose input interface such as SetEventDoseGy(G4double doseGy) and/or "
                "WriteEvent(const G4Event* event, G4double edepMeV, G4double doseGy). "
                "The one-argument WriteEvent adapter may use cached currentEventDoseGy_ "
                "that upstream action/scoring code can set."
            ),
            (
                "Keep CSV/JSON writing in OutputManager only, and keep ScoringManager out "
                "of OutputManager includes and calls."
            ),
            (
                "Read G4_OUTPUT_DIR for runtime artifact output and write fixed filenames "
                "output.csv, run_summary.json, and metadata.json. output.csv must include "
                "the header EventID,edep_MeV,dose_Gy."
            ),
            (
                'OutputManager.cc must contain a direct literal call std::getenv("G4_OUTPUT_DIR") '
                'or getenv("G4_OUTPUT_DIR"). Do not pass a variable such as kEnvOutputDir to '
                "getenv, even if that variable stores the same string."
            ),
            (
                "Do not define EventData and do not depend on G4VUserEventInformation or "
                "G4Event::GetUserInformation. Accumulate event edep from "
                "RecordStep(const G4Step*) using step->GetTotalEnergyDeposit(), reset it "
                "in BeginEvent, and write it in WriteEvent(const G4Event*)."
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
                "Provide static MaterialRegistry* GetInstance() returning the address of "
                "a function-local static MaterialRegistry so other modules can share the registry."
            ),
            (
                "Use valid Geant4 G4Exception severity values such as FatalException "
                "or FatalErrorInArgument; do not write FatalErrorInArguments."
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
                "runManager->Initialize(), and comments should not contain that exact "
                "call token."
            ),
            (
                "main.cc must include ActionInitialization.hh and register "
                "new ActionInitialization() with the run manager."
            ),
            (
                "Do not define RunAction, EventAction, SteppingAction, or "
                "ActionInitialization classes inside main.cc."
            ),
            (
                "Do not call OutputManager::Instance() or ScoringManager::Instance() "
                "from main.cc; generated action modules own runtime callbacks."
            ),
            (
                "Use the real DetectorConstruction constructor from the generated "
                "header; if it takes MaterialRegistry*, obtain the registry with "
                "MaterialRegistry::GetInstance(), initialize it, and pass it to "
                "DetectorConstruction."
            ),
            "Do not call new MaterialRegistry(); its constructor may be private.",
            (
                "If DetectorConstruction only has a default constructor, call "
                "new DetectorConstruction() and do not pass MaterialRegistry."
            ),
        ]
    if module_name == "placement":
        return [
            (
                "Every out-of-class PlacementManager::Place(...) definition in "
                "PlacementManager.cc must have a matching static Place(...) declaration "
                "with the same parameter order and types in PlacementManager.hh."
            ),
            (
                "Prefer the compatibility signature "
                "static G4VPhysicalVolume* Place(G4LogicalVolume* logical, "
                "const G4ThreeVector& position, G4RotationMatrix* rotation, "
                "G4LogicalVolume* mother, G4bool checkOverlaps = true)."
            ),
        ]
    return []
