"""Build module context for each module agent."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.module_agents.module_context_examples import (
    build_context_retrieval_policy,
    get_module_code_example,
    get_module_interface_context,
)
from agent_core.g4_codegen.schemas import ModuleContext
from agent_core.workspace.paths import STAGE_CODEGEN


def build_module_context(
    module_name: str,
    module_contract: dict[str, Any],
    g4_model_ir: dict[str, Any],
    codegen_plan: dict[str, Any],
    geometry_strategy_plan: dict[str, Any],
    code_architecture_plan: dict[str, Any],
    job_id: str,
    run_mode: str = "strict",
    previous_failures: list[dict[str, Any]] | None = None,
    existing_file_summaries: list[dict[str, Any]] | None = None,
    rag_context: list[dict[str, Any]] | None = None,
    rag_score: float | None = None,
    web_context: list[dict[str, Any]] | None = None,
    context_decision: str | None = None,
    web_search_available: bool | None = None,
    runtime_failure_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build context for a module agent.

    Extracts relevant subset of G4ModelIR and adds planning context.
    """
    # Extract relevant IR subset
    ir_subset = _extract_ir_subset(module_name, g4_model_ir)

    # Get Geant4 API rules
    api_rules = _get_geant4_api_rules(module_name)
    selected_rag = _select_context_snippets(module_name, rag_context or [])
    selected_web = _select_context_snippets(module_name, web_context or [])

    context = ModuleContext(
        module_name=module_name,
        module_contract=module_contract,
        g4_model_ir_subset=ir_subset,
        codegen_plan=codegen_plan,
        geometry_strategy_plan=geometry_strategy_plan,
        code_architecture_plan=code_architecture_plan,
        rag_snippets=selected_rag,
        web_context=selected_web,
        geant4_api_rules=api_rules,
        module_code_example=get_module_code_example(module_name),
        interface_context=get_module_interface_context(module_name),
        context_retrieval_policy=build_context_retrieval_policy(
            rag_score=rag_score,
            context_decision=context_decision,
            web_search_available=web_search_available,
        ),
        existing_generated_file_summaries=existing_file_summaries or [],
        previous_failures=previous_failures or [],
        runtime_failure_context=runtime_failure_context or {},
        run_mode=run_mode,
    )

    # Persist
    from agent_core.workspace.io import get_job_dir

    ctx_dir = get_job_dir(job_id) / STAGE_CODEGEN / "module_contexts"
    ctx_dir.mkdir(parents=True, exist_ok=True)

    ctx_path = ctx_dir / f"{module_name}.json"
    context_data = context.model_dump()
    context_data["job_id"] = job_id

    ctx_path.write_text(json.dumps(context_data, indent=2, ensure_ascii=False))

    return context_data


def _select_context_snippets(
    module_name: str,
    context_entries: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Select RAG/web snippets relevant to a module without losing global facts."""
    if not context_entries:
        return []

    keywords = _module_context_keywords(module_name)
    selected: list[dict[str, Any]] = []
    global_entries: list[dict[str, Any]] = []
    for entry in context_entries:
        text = json.dumps(entry, ensure_ascii=False).lower()
        if any(keyword in text for keyword in keywords):
            selected.append(entry)
        elif any(keyword in text for keyword in ("geant4", "g4", "cmake", "run manager")):
            global_entries.append(entry)

    combined = selected + global_entries
    if not combined:
        combined = context_entries
    return combined[:limit]


def _module_context_keywords(module_name: str) -> set[str]:
    common = {"geant4", "g4", "cmake", "run manager"}
    by_module = {
        "simulation_core": {
            "material",
            "g4material",
            "g4nistmanager",
            "nist",
            "geometry",
            "detectorconstruction",
            "placement",
            "g4pvplacement",
            "logicalvolume",
            "sensitive",
            "processhits",
            "hitscollection",
            "scoring",
            "dose",
            "edep",
            "step limit",
            "production cut",
        },
        "beam_physics": {
            "source",
            "particlegun",
            "primarygenerator",
            "gps",
            "physics",
            "physlist",
            "ftfp_bert",
            "qgsp",
            "production cut",
            "range cut",
        },
        "runtime_app": {
            "output",
            "csv",
            "json",
            "metadata",
            "actioninitialization",
            "runaction",
            "eventaction",
            "steppingaction",
            "main.cc",
            "cmakelists",
            "executable",
            "macro",
            "run manager",
        },
    }
    return common | by_module.get(module_name, set())


def _extract_ir_subset(module_name: str, g4_model_ir: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant subset of G4ModelIR for a module."""
    subset: dict[str, Any] = {
        "model_ir_id": g4_model_ir.get("model_ir_id", ""),
        "job_id": g4_model_ir.get("job_id", ""),
        "modeling_mode": g4_model_ir.get("modeling_mode", "realistic"),
    }

    if module_name == "simulation_core":
        subset["components"] = g4_model_ir.get("components", [])
        subset["materials"] = g4_model_ir.get("materials", [])
        subset["scoring"] = g4_model_ir.get("scoring", [])
        subset["sensitive_detectors"] = g4_model_ir.get("sensitive_detectors", [])

    if module_name == "beam_physics":
        subset["sources"] = g4_model_ir.get("sources", [])
        subset["physics"] = g4_model_ir.get("physics", {})
        subset["scoring"] = g4_model_ir.get("scoring", [])

    if module_name == "runtime_app":
        subset["components"] = g4_model_ir.get("components", [])
        subset["sources"] = g4_model_ir.get("sources", [])
        subset["physics"] = g4_model_ir.get("physics", {})
        subset["scoring"] = g4_model_ir.get("scoring", [])
        subset["sensitive_detectors"] = g4_model_ir.get("sensitive_detectors", [])

    return subset


def _get_geant4_api_rules(module_name: str) -> list[str]:
    """Get Geant4 API rules relevant to a module."""
    common_rules = [
        "使用 G4SystemOfUnits.hh 中的单位常量",
        "不要实例化抽象基类",
        "使用 G4NistManager 获取 NIST 材料",
        "LogicalVolume 必须有 Material",
        "PhysicalVolume 必须有 Mother Volume",
    ]

    module_rules: dict[str, list[str]] = {
        "simulation_core": [
            "材料、几何、放置、SensitiveDetector、Hit 和 ScoringManager 必须在同一接口模型下生成",
            "不得把 unsupported geometry 简化成 G4Box；如无法建模必须显式暴露 unsupported feature",
            "box dimensions 中 dx/dy/dz 表示全长；构造 G4Box 时使用 half-length 并乘以全局长度单位",
            "placement position 坐标不要缩放；按 IR 数值乘以全局长度单位",
            "SensitiveDetector 必须注册到 G4SDManager，并在 geometry 初始化时 "
            "attach 到真实 logical volume",
            "dose_Gy 必须基于真实能量沉积和质量/体积/密度关系，不能写固定占位值",
            "需要精度控制时显式建模 production cuts、range cuts、step limiter 或用户 limits",
        ],
        "beam_physics": [
            "PrimaryGeneratorAction 必须使用 IR 中的粒子、能量、位置和方向，不得默认改粒子或能量",
            "物理列表选择必须与粒子类型、能量范围和材料/探测器任务相匹配",
            "生产截断、range cut 或精度控制必须与 scoring 需求一致，不能仅保留 Geant4 默认值",
            "使用 G4SystemOfUnits.hh 中的单位常量",
        ],
        "runtime_app": [
            "main.cc 必须使用实际生成的 DetectorConstruction、"
            "PhysicsListFactoryWrapper 和 ActionInitialization 接口",
            "CMakeLists.txt 必须包含所有生成的 src/*.cc 和 main.cc，"
            "设置足够的 C++ 标准，并启用 Geant4 UI/Vis/Qt 交互依赖",
            "main.cc 必须参考 Geant4 B1 示例：无宏脚本参数时创建 UIExecutive "
            "并打开交互 UI；有宏脚本参数时通过 UImanager 执行 batch macro",
            "RunAction/EventAction/SteppingAction 必须真实连接 OutputManager 和 scoring 数据流",
            "OutputManager 必须优先写入 G4_OUTPUT_DIR 环境变量指向的目录",
            "输出目录必须包含 g4_summary.json、provenance.json、event_table.csv、"
            "edep_3d.csv、dose_3d.csv",
            "event_table.csv header 必须包含 EventID,edep_MeV,dose_Gy，"
            "且每个事件至少一行真实沉积/剂量",
            "edep_3d.csv 和 dose_3d.csv 必须包含坐标列与非零 "
            "edep_MeV/dose_Gy bin，不能只依赖 scoring.csv",
            "不要依赖目标环境不支持的 /score UI 命令；若使用 scoring 宏，"
            "必须确保 G4ScoringManager 初始化且命令真实可用",
        ],
    }

    return common_rules + module_rules.get(module_name, [])
