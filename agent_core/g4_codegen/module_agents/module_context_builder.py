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
        run_mode=run_mode,
    )

    # Persist
    from agent_core.config.workspace import get_job_dir

    ctx_dir = get_job_dir(job_id) / "06_codegen" / "module_contexts"
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
        "material": {"material", "g4material", "g4nistmanager", "nist"},
        "geometry": {"geometry", "detectorconstruction", "g4box", "logicalvolume"},
        "placement": {"placement", "g4pvplacement", "rotation", "transform"},
        "source": {"source", "particlegun", "primarygenerator"},
        "physics": {"physics", "physlist", "ftfp_bert", "production cut"},
        "sensitive_detector": {"sensitive", "processhits", "hitscollection", "hit"},
        "scoring": {"scoring", "scoremap", "scoringmesh", "primitive scorer"},
        "output_manager": {"output", "csv", "json", "metadata", "file"},
        "action_initialization": {"actioninitialization", "runaction", "user action"},
        "main_cmake": {"main.cc", "cmakelists", "executable", "macro"},
    }
    return common | by_module.get(module_name, set())


def _extract_ir_subset(module_name: str, g4_model_ir: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant subset of G4ModelIR for a module."""
    subset: dict[str, Any] = {
        "model_ir_id": g4_model_ir.get("model_ir_id", ""),
        "job_id": g4_model_ir.get("job_id", ""),
        "modeling_mode": g4_model_ir.get("modeling_mode", "realistic"),
    }

    if module_name in ("material", "geometry", "placement"):
        subset["components"] = g4_model_ir.get("components", [])
        subset["materials"] = g4_model_ir.get("materials", [])

    if module_name in ("source",):
        subset["sources"] = g4_model_ir.get("sources", [])

    if module_name in ("physics",):
        subset["physics"] = g4_model_ir.get("physics", {})

    if module_name in ("sensitive_detector", "scoring"):
        subset["scoring"] = g4_model_ir.get("scoring", [])
        subset["components"] = g4_model_ir.get("components", [])
        subset["materials"] = g4_model_ir.get("materials", [])
        subset["sensitive_detectors"] = g4_model_ir.get("sensitive_detectors", [])

    if module_name in ("output_manager",):
        subset["scoring"] = g4_model_ir.get("scoring", [])
        subset["sources"] = g4_model_ir.get("sources", [])

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
        "material": [
            "G4NistManager::Instance()->FindOrBuildMaterial() 用于 NIST 材料",
            "自定义材料使用 new G4Material(name, density, ncomponents) 后 AddElement(...)",
        ],
        "geometry": [
            "G4VUserDetectorConstruction::Construct() 返回 world LV",
            "Solid 创建后不可修改",
            (
                "G4ModelIR global_units.length 默认是 mm；所有 component dimensions "
                "和 placement position 都按该单位解释"
            ),
            (
                "box dimensions 中 dx/dy/dz 表示全长；构造 G4Box 时必须传 "
                "half-length: dx/2、dy/2、dz/2，并乘以 mm"
            ),
            "placement position 坐标不要缩放；按 IR 数值乘以 mm",
            "材料查找必须通过 MaterialRegistry，不要在 geometry 模块直接调用 G4NistManager",
            "world 物理体可直接构造为 null mother；非 world 物理体放置必须通过 PlacementManager",
            (
                "PlacementManager 预期接口：PlaceVolume(logical, name, mother, position, "
                "rotation, copy_no, check_overlaps)"
            ),
        ],
        "placement": [
            "G4PVPlacement 需要 rotation matrix 和 translation vector",
            "checkOverlaps 默认开启",
        ],
        "source": [
            "G4ParticleGun 或 G4GeneralParticleSource",
            "能量和方向必须设置",
        ],
        "physics": [
            "G4VModularPhysicsList 需要 RegisterPhysics()",
            "FTFP_BERT 是通用推荐",
        ],
        "sensitive_detector": [
            "G4VSensitiveDetector::ProcessHits() 必须实现",
            "Hit 必须实现 draw() 和 print()",
        ],
        "scoring": [
            (
                "如使用 primitive scoring，可使用 G4MultiFunctionalDetector 和 "
                "G4VPrimitiveScorer；不要声称已注册未实现的 scorer"
            ),
            (
                "不得硬编码 detector mass；dose_Gy 必须基于 IR 中几何尺寸和材料密度计算，"
                "或通过显式接口参数传入质量"
            ),
            "能量沉积以 Geant4 内部能量单位累计；转换到 J 时使用 edep / joule，不要乘以 MeV",
            "不要 SetSensitiveDetector 或覆盖 sensitive_detector 模块的 ownership",
            "不要写 CSV/JSON 文件；输出由 output_manager 模块负责",
        ],
        "output_manager": [
            "文件 I/O 在 BeginOfRunAction 和 EndOfRunAction 中处理",
        ],
        "action_initialization": [
            "Build() 方法注册所有 user actions",
        ],
        "main_cmake": [
            "find_package(Geant4 REQUIRED)",
            "include(${Geant4_USE_FILE})",
        ],
    }

    return common_rules + module_rules.get(module_name, [])
