"""子图节点: 展示完整仿真计划，interrupt 等待用户确认"""

from typing import Literal

from langgraph.types import Command, interrupt

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.schemas import SimulationPlan
from radagent.subgraphs.research.state import ResearchState

_NODE = "confirm_params"


def confirm_params(state: ResearchState) -> Command[Literal["__end__", "design_schema"]]:
    """整合为 SimulationPlan，interrupt 让用户确认"""
    log_node_entry(_NODE, state)

    geometry = state.get("geometry")
    orbit = state.get("orbit")
    scenarios = state.get("scenarios", [])
    orbit_env = state.get("orbit_env_data", {})
    search_results = state.get("search_results", "")

    if not geometry:
        log_error(_NODE, "缺少屏蔽几何信息")
        update = {"parse_error": "缺少屏蔽几何信息，无法生成仿真计划"}
        log_node_exit(_NODE, "design_schema", update)
        return Command(update=update, goto="design_schema")

    plan = SimulationPlan(
        geometry=geometry,
        orbit=orbit,
        scenarios=tuple(scenarios),
        notes=f"数据来源: {orbit_env.get('model', '未知')} | {orbit_env.get('reference', '')}",
    )

    # 构建展示信息
    message = _format_plan_message(plan, orbit_env, search_results)
    log_info(_NODE, f"仿真计划已构建: {geometry.name}, {len(scenarios)} 场景")

    decision = interrupt({
        "type": "plan_confirmation",
        "message": message,
        "plan": {
            "geometry": {
                "name": geometry.name,
                "layers": [
                    {"name": l.name, "material": l.material,
                     "geant4": l.geant4_material, "thickness_mm": l.thickness_mm,
                     "role": l.role}
                    for l in geometry.layers
                ],
                "sensitive_volume": geometry.sensitive_volume,
            },
            "orbit": {"name": orbit.orbit_name, "altitude_km": orbit.altitude_km,
                      "inclination_deg": orbit.inclination_deg} if orbit else None,
            "scenarios": [
                {"name": s.name, "particle": s.source.particle,
                 "energy_MeV": s.source.energy_MeV, "num_events": s.num_events,
                 "physics_list": s.physics_list}
                for s in scenarios
            ],
        },
    })

    action = decision.get("action", "confirm")

    if action == "modify":
        feedback = decision.get("feedback", "")
        log_info(_NODE, f"用户修改: {feedback}")
        update = {"parse_error": f"用户修改: {feedback}"}
        log_node_exit(_NODE, "design_schema", update)
        return Command(update=update, goto="design_schema")
    elif action == "cancel":
        log_info(_NODE, "用户取消仿真")
        update = {"parse_error": "用户取消仿真"}
        log_node_exit(_NODE, "__end__", update)
        return Command(update=update, goto="__end__")
    else:
        update = {"sim_plan": plan, "parse_error": ""}
        log_node_exit(_NODE, "__end__", update)
        return Command(update=update, goto="__end__")


def _format_plan_message(plan: SimulationPlan, orbit_env: dict, search_results: str) -> str:
    """格式化仿真计划展示"""
    lines = ["=== 仿真计划 ===\n"]

    # 几何结构
    lines.append(f"屏蔽结构: {plan.geometry.name}")
    lines.append(f"横截面: {plan.geometry.size_xy_cm} cm x {plan.geometry.size_xy_cm} cm")
    lines.append("层结构 (从外到内):")
    for i, layer in enumerate(plan.geometry.layers, 1):
        lines.append(f"  {i}. {layer.name}: {layer.material} ({layer.geant4_material}) "
                      f"{layer.thickness_mm} mm, ρ={layer.density_g_cm3} g/cm³ [{layer.role}]")
    if plan.geometry.sensitive_volume:
        lines.append(f"敏感体积: {plan.geometry.sensitive_volume}")

    # 轨道
    if plan.orbit:
        lines.append(f"\n轨道: {plan.orbit.orbit_name} ({plan.orbit.altitude_km} km, "
                      f"倾角 {plan.orbit.inclination_deg}°)")
        if orbit_env.get("notes"):
            lines.append(f"  {orbit_env['notes']}")

    # 仿真场景
    lines.append(f"\n仿真场景 ({len(plan.scenarios)} 个):")
    for s in plan.scenarios:
        lines.append(f"  - {s.name}: {s.source.particle} {s.source.energy_MeV} MeV, "
                      f"{s.num_events} events, {s.physics_list}")

    # 数据来源
    lines.append(f"\n数据来源: {orbit_env.get('model', '未知')}")
    if search_results:
        lines.append(f"搜索参考: {search_results[:200]}...")

    lines.append("\n请确认 / 修改 / 取消")

    return "\n".join(lines)
