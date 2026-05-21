"""子图节点: 展示完整仿真计划，interrupt 等待用户确认"""

import re
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command, interrupt

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import ParticleSource, SimulationPlan, SimulationScenario
from radagent.subgraphs.research.state import ResearchState
from radagent.tools.knowledge import recommend_physics, try_lookup_particle
from radagent.tools.model_router import get_light_llm

llm = get_light_llm()

_NODE = "confirm_params"

_MODIFY_PARSE_PROMPT = """你是仿真参数解析专家。用户对仿真计划提出了修改意见，请解析为结构化场景列表。

当前计划有 {n_existing} 个场景。
用户修改意见: {feedback}

返回 JSON 数组（不要其他内容）:
[
    {{
        "name": "场景名",
        "particle": "粒子名",
        "energy_per_nucleon_MeV": 核子能量或null,
        "energy_MeV": 总能量或null,
        "num_events": 事件数,
        "physics_list": "物理列表名或auto",
        "source_type": "parallel_beam/isotropic/hemisphere或null"
    }}
]

注意:
- 如果用户说了 "400MeV/n 碳离子" 则 particle=C_ion, energy_per_nucleon_MeV=400
- 如果用户只说了总能量则 energy_MeV=数值
- physics_list 用户未指定则填 "auto"
- source_type 用户未指定则填 null（保持默认）
- 必须返回所有场景（不是只返回修改的）"""


def confirm_params(state: ResearchState) -> Command[Literal["__end__", "design_schema", "confirm_params"]]:
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
                 "energy_MeV": s.source.energy_MeV,
                 "energy_per_nucleon_MeV": s.source.energy_per_nucleon_MeV,
                 "num_events": s.num_events,
                 "physics_list": s.physics_list,
                 "source_type": s.source.source_type,
                 "has_spectrum": bool(s.source.energy_spectrum)}
                for s in scenarios
            ],
        },
    })

    action = decision.get("action", "confirm")

    if action == "modify":
        feedback = decision.get("feedback", "")
        log_info(_NODE, f"用户修改: {feedback}")

        # 尝试解析用户反馈中的场景修改
        updated_scenarios = _parse_modify_feedback(feedback, scenarios)

        if updated_scenarios:
            log_info(_NODE, f"场景已更新: {len(updated_scenarios)} 个场景")
            for s in updated_scenarios:
                epn = s.source.energy_per_nucleon_MeV
                e_str = f"{epn} MeV/n" if epn else f"{s.source.energy_MeV} MeV"
                log_info(_NODE, f"  {s.name}: {s.source.particle} {e_str}, "
                          f"{s.num_events} events, {s.physics_list}")

            update = {"scenarios": updated_scenarios, "parse_error": ""}
            log_node_exit(_NODE, "confirm_params (重新确认)", update)
            return Command(update=update, goto="confirm_params")
        else:
            # 无法解析，回退到 design_schema
            log_info(_NODE, "无法解析修改，回退到 design_schema")
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


def _parse_modify_feedback(feedback: str, current_scenarios: list) -> list[SimulationScenario] | None:
    """解析用户修改反馈，尝试提取场景变更。优先正则提取，降级到 LLM 解析。"""
    # 快速路径：正则匹配 "场景X: particle energy events physics" 格式
    parsed = _regex_parse_scenarios(feedback)
    if parsed:
        return parsed

    # LLM 解析
    if llm:
        return _llm_parse_scenarios(feedback, len(current_scenarios))

    return None


def _regex_parse_scenarios(text: str) -> list[SimulationScenario] | None:
    """用正则从反馈文本中提取场景"""
    # 匹配: 场景A: C_ion 400 MeV/n (总能量 4800 MeV), 500000 events, FTFP_BERT
    pattern = (
        r"场景([A-Z])\s*[:：]\s*"
        r"(\S+)\s+"            # particle
        r"([\d.]+)\s*"         # energy number
        r"(MeV/n|MeV)"         # unit
        r"(?:\s*\(总能量\s*([\d.]+)\s*MeV\))?"  # optional total energy
        r"\s*,?\s*"
        r"(\d+)\s*events"      # num_events
        r"\s*,?\s*"
        r"(\S+)"               # physics_list
    )
    matches = list(re.finditer(pattern, text))
    if not matches:
        return None

    scenarios = []
    for m in matches:
        label, particle_raw, energy_str, unit, total_str, events_str, physics = m.groups()
        particle = try_lookup_particle(particle_raw) or particle_raw
        energy_val = float(energy_str)
        num_events = int(events_str)

        if unit == "MeV/n":
            energy_per_nuc = energy_val
            if total_str:
                energy_total = float(total_str)
            else:
                energy_total = None
        else:
            energy_per_nuc = None
            energy_total = energy_val

        # 如果有 per_nucleon 但没 total，计算
        if energy_per_nuc and not energy_total:
            from radagent.tools.knowledge import CUSTOM_PARTICLES
            ion_info = CUSTOM_PARTICLES.get(particle)
            if ion_info:
                energy_total = energy_per_nuc * ion_info["A"]

        physics_list = physics if physics != "auto" else recommend_physics(particle, energy_total or 100)

        scenarios.append(SimulationScenario(
            name=f"场景{label}",
            source=ParticleSource(
                particle=particle,
                energy_MeV=energy_total,
                energy_per_nucleon_MeV=energy_per_nuc,
                direction=(0, 0, -1),
            ),
            num_events=num_events,
            physics_list=physics_list,
        ))

    return scenarios if scenarios else None


def _llm_parse_scenarios(feedback: str, n_existing: int) -> list[SimulationScenario] | None:
    """用 LLM 解析用户修改反馈中的场景"""
    prompt = _MODIFY_PARSE_PROMPT.format(n_existing=n_existing, feedback=feedback)
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        log_llm_call(_NODE, prompt, content)

        # 提取 JSON
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        import json
        parsed = json.loads(content)
        if not isinstance(parsed, list):
            return None

        scenarios = []
        for i, item in enumerate(parsed):
            raw_particle = item.get("particle", "proton")
            particle = try_lookup_particle(raw_particle) or raw_particle

            energy_per_nuc = item.get("energy_per_nucleon_MeV")
            energy_total = item.get("energy_MeV")
            num_events = item.get("num_events", 100000)
            physics = item.get("physics_list", "auto")

            if energy_per_nuc and not energy_total:
                from radagent.tools.knowledge import CUSTOM_PARTICLES
                ion_info = CUSTOM_PARTICLES.get(particle)
                if ion_info:
                    energy_total = energy_per_nuc * ion_info["A"]

            if physics == "auto":
                physics = recommend_physics(particle, energy_total or 100)

            source_type = item.get("source_type") or "parallel_beam"

            scenarios.append(SimulationScenario(
                name=item.get("name", f"场景{chr(65+i)}"),
                source=ParticleSource(
                    particle=particle,
                    energy_MeV=energy_total,
                    energy_per_nucleon_MeV=energy_per_nuc,
                    source_type=source_type,
                    direction=(0, 0, -1),
                ),
                num_events=int(num_events),
                physics_list=physics,
            ))

        return scenarios if scenarios else None

    except Exception as e:
        log_error(_NODE, f"LLM 场景解析失败: {e}")
        return None


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
        epn = s.source.energy_per_nucleon_MeV
        if s.source.energy_spectrum:
            spec = s.source.energy_spectrum
            e_str = f"能谱 [{spec[0]}-{spec[-1]}] MeV ({len(spec)} 点)"
        elif epn:
            total = s.source.energy_MeV
            total_str = f"{total:.0f}" if total else "?"
            e_str = f"{epn} MeV/n (总能量 {total_str} MeV)"
        elif s.source.energy_MeV:
            e_str = f"{s.source.energy_MeV} MeV"
        else:
            e_str = "未指定能量"
        src_type = s.source.source_type or "parallel_beam"
        lines.append(f"  - {s.name}: {s.source.particle} {e_str}, "
                      f"{s.num_events} events, {s.physics_list}, 源类型={src_type}")

    # 数据来源
    lines.append(f"\n数据来源: {orbit_env.get('model', '未知')}")
    if search_results:
        lines.append(f"搜索参考: {search_results[:200]}...")

    lines.append("\n请确认 / 修改 / 取消")

    return "\n".join(lines)
