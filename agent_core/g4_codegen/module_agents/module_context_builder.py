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
    global_units = _normalize_global_units(g4_model_ir.get("global_units"))
    coordinate_system = _normalize_coordinate_system(
        g4_model_ir.get("coordinate_system"),
        global_units=global_units,
    )
    subset: dict[str, Any] = {
        "model_ir_id": g4_model_ir.get("model_ir_id", ""),
        "job_id": g4_model_ir.get("job_id", ""),
        "modeling_mode": g4_model_ir.get("modeling_mode", "realistic"),
        "target_system": g4_model_ir.get("target_system", ""),
        "global_units": global_units,
        "coordinate_system": coordinate_system,
        "unit_contract": _build_unit_contract(
            global_units=global_units,
            coordinate_system=coordinate_system,
        ),
    }

    if module_name == "simulation_core":
        subset["components"] = g4_model_ir.get("components", [])
        subset["interfaces"] = g4_model_ir.get("interfaces", [])
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


def _normalize_global_units(raw_units: Any) -> dict[str, str]:
    units = {
        "length": "um",
        "energy": "MeV",
        "dose": "Gy",
        "time": "s",
    }
    data = _as_mapping(raw_units)
    for key in units:
        value = data.get(key)
        if value:
            units[key] = str(value)
    return units


def _normalize_coordinate_system(
    raw_coordinate_system: Any,
    *,
    global_units: dict[str, str],
) -> dict[str, Any]:
    coordinate_system: dict[str, Any] = {
        "system": "cartesian",
        "origin_definition": "world_center",
        "axis_definition": {
            "x": "sensor_width",
            "y": "sensor_length",
            "z": "beam_direction",
        },
        "unit": global_units["length"],
    }
    data = _as_mapping(raw_coordinate_system)
    for key in ("system", "origin_definition", "axis_definition", "unit"):
        value = data.get(key)
        if value:
            coordinate_system[key] = value
    if not coordinate_system.get("unit"):
        coordinate_system["unit"] = global_units["length"]
    return coordinate_system


def _build_unit_contract(
    *,
    global_units: dict[str, str],
    coordinate_system: dict[str, Any],
) -> dict[str, str]:
    length_unit = global_units["length"]
    coordinate_unit = str(coordinate_system.get("unit") or length_unit)
    return {
        "length_unit": length_unit,
        "coordinate_unit": coordinate_unit,
        "energy_unit": global_units["energy"],
        "dose_unit": global_units["dose"],
        "time_unit": global_units["time"],
        "dimension_semantics": (
            "Component dimensions are full physical lengths in global_units.length "
            "unless a key is explicitly named half_x, half_y, or half_z."
        ),
        "box_dimension_rule": (
            "For G4Box, dx/dy/dz are full lengths; pass (dx/2), (dy/2), "
            f"and (dz/2) multiplied by the Geant4 unit constant {length_unit}."
        ),
        "placement_rule": (
            "Placement position coordinates are translations in coordinate_system.unit; "
            f"multiply x/y/z by the Geant4 unit constant {coordinate_unit}."
        ),
        "voxel_rule": (
            "Voxel grid sizes are full bin dimensions in global_units.length; "
            f"use the Geant4 unit constant {length_unit}."
        ),
        "unit_source": "g4_model_ir.global_units and g4_model_ir.coordinate_system",
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        data = value.model_dump(mode="json")
        return data if isinstance(data, dict) else {}
    return {}


def _get_geant4_api_rules(module_name: str) -> list[str]:
    """Get Geant4 API rules relevant to a module."""
    common_rules = [
        "使用 G4SystemOfUnits.hh 中的单位常量",
        "ModuleContext.g4_model_ir_subset.unit_contract 是单位、尺寸和位置语义的唯一准则；不得默认使用 mm",
        "不要实例化抽象基类",
        "使用 G4NistManager 获取 NIST 材料",
        "LogicalVolume 必须有 Material",
        "PhysicalVolume 必须有 Mother Volume",
    ]

    module_rules: dict[str, list[str]] = {
        "simulation_core": [
            "材料、几何、放置、SensitiveDetector、Hit 和 ScoringManager 必须在同一接口模型下生成",
            "不得把 unsupported geometry 简化成 G4Box；如无法建模必须显式暴露 unsupported feature",
            "box dimensions 中 dx/dy/dz 表示全长；构造 G4Box 时使用 half-length 并乘以 unit_contract.length_unit",
            "placement position 坐标不要缩放；按 IR 数值乘以 unit_contract.coordinate_unit",
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
            "CMakeLists.txt 直接使用 module_code_example.cmake_template 字段"
            "（Geant4 B1 模板：find_package ui_all vis_all + file(GLOB src/*.cc "
            "include/*.hh)），原样输出即可，所有生成源文件会被自动编译；"
            "不要从零编写 CMake、也不要手列源文件。集成装配器会强制使用该模板",
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
