"""Build module context for each module agent."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import ModuleContext


def build_module_context(
    module_name: str,
    module_contract: dict[str, Any],
    g4_model_ir: dict[str, Any],
    codegen_plan: dict[str, Any],
    geometry_strategy_plan: dict[str, Any],
    code_architecture_plan: dict[str, Any],
    job_id: str,
    run_mode: str = "dev",
    previous_failures: list[dict[str, Any]] | None = None,
    existing_file_summaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build context for a module agent.

    Extracts relevant subset of G4ModelIR and adds planning context.
    """
    # Extract relevant IR subset
    ir_subset = _extract_ir_subset(module_name, g4_model_ir)

    # Get Geant4 API rules
    api_rules = _get_geant4_api_rules(module_name)

    context = ModuleContext(
        module_name=module_name,
        module_contract=module_contract,
        g4_model_ir_subset=ir_subset,
        codegen_plan=codegen_plan,
        geometry_strategy_plan=geometry_strategy_plan,
        code_architecture_plan=code_architecture_plan,
        rag_snippets=[],
        geant4_api_rules=api_rules,
        existing_generated_file_summaries=existing_file_summaries or [],
        previous_failures=previous_failures or [],
        run_mode=run_mode,
    )

    # Persist
    from agent_core.config.workspace import get_job_dir
    ctx_dir = get_job_dir(job_id) / "06_codegen" / "module_contexts"
    ctx_dir.mkdir(parents=True, exist_ok=True)

    ctx_path = ctx_dir / f"{module_name}.json"
    ctx_path.write_text(
        json.dumps(context.model_dump(), indent=2, ensure_ascii=False)
    )

    return context.model_dump()


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
            "自定义材料使用 G4Material::Create()",
        ],
        "geometry": [
            "G4VUserDetectorConstruction::Construct() 返回 world LV",
            "Solid 创建后不可修改",
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
            "G4MultiFunctionalDetector 用于 primitive scoring",
            "G4VPrimitiveScorer 需要注册到 detector",
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
