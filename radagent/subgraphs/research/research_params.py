"""子图节点: Web 搜索 + SpacePy 查询轨道辐射环境和材料属性，填充仿真场景"""

import math
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.schemas import ParticleSource, SimulationScenario
from radagent.tools.knowledge import recommend_physics
from radagent.tools.orbit_query import query_radiation_environment
from radagent.tools.web_search import search_parameter_recommendation
from radagent.subgraphs.research.state import ResearchState

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0)
except Exception:
    llm = None

_NODE = "research_params"


def research_params(state: ResearchState) -> Command[Literal["confirm_params"]]:
    """查询轨道辐射环境 + 生成仿真场景"""
    log_node_entry(_NODE, state)

    geometry = state.get("geometry")
    orbit = state.get("orbit")

    if not geometry:
        log_error(_NODE, "缺少屏蔽几何信息")
        update = {"parse_error": "缺少屏蔽几何信息"}
        log_node_exit(_NODE, "confirm_params", update)
        return Command(update=update, goto="confirm_params")

    # 1. 查询轨道辐射环境
    orbit_env = {}
    if orbit:
        log_info(_NODE, f"查询轨道辐射环境: {orbit.orbit_name} ({orbit.altitude_km} km)")
        orbit_env = query_radiation_environment(
            altitude_km=orbit.altitude_km,
            inclination_deg=orbit.inclination_deg,
        )
        log_info(_NODE, f"轨道环境结果: model={orbit_env.get('model')}, "
                  f"proton={orbit_env.get('proton', {})}, electron={orbit_env.get('electron', {})}")

    # 2. Web 搜索材料辐射特性
    materials = ", ".join(layer.material for layer in geometry.layers)
    log_info(_NODE, f"搜索材料辐射特性: {materials}")
    search_results = search_parameter_recommendation(
        particle="proton" if orbit and "质子" in orbit_env.get("notes", "") else None,
        material=materials,
        scenario=state.get("user_input", ""),
    )
    log_info(_NODE, f"搜索结果长度: {len(search_results)} 字符")

    # 3. 根据轨道环境生成仿真场景
    scenarios = _generate_scenarios(orbit, orbit_env, geometry)
    log_info(_NODE, f"生成 {len(scenarios)} 个仿真场景:")
    for s in scenarios:
        log_info(_NODE, f"  {s.name}: {s.source.particle} {s.source.energy_MeV} MeV, "
                  f"{s.num_events} events, {s.physics_list}")

    update = {
        "scenarios": scenarios,
        "orbit_env_data": orbit_env,
        "search_results": search_results,
        "parse_error": "",
    }
    log_node_exit(_NODE, "confirm_params", update)
    return Command(update=update, goto="confirm_params")


def _generate_scenarios(orbit, orbit_env: dict, geometry) -> list[SimulationScenario]:
    """根据轨道环境生成默认仿真场景"""
    scenarios = []

    if orbit and orbit_env:
        # 质子场景
        proton_data = orbit_env.get("proton", {})
        if proton_data:
            energy_range = proton_data.get("energy_range_MeV", [10, 400])
            energies = _pick_energy_points(energy_range)
            for e in energies:
                particle = "proton"
                scenarios.append(SimulationScenario(
                    name=f"{orbit.orbit_name} 质子 {e} MeV",
                    source=ParticleSource(
                        particle=particle,
                        energy_MeV=e,
                        direction=(0, 0, -1),
                    ),
                    num_events=100000,
                    physics_list=recommend_physics(particle, e),
                ))

        # 电子场景
        electron_data = orbit_env.get("electron", {})
        if electron_data and electron_data.get("integral_flux_cm2_s"):
            energy_range = electron_data.get("energy_range_MeV", [0.5, 7])
            energies = _pick_energy_points(energy_range)
            for e in energies:
                particle = "e-"
                scenarios.append(SimulationScenario(
                    name=f"{orbit.orbit_name} 电子 {e} MeV",
                    source=ParticleSource(
                        particle=particle,
                        energy_MeV=e,
                        direction=(0, 0, -1),
                    ),
                    num_events=100000,
                    physics_list=recommend_physics(particle, e),
                ))

    # 如果没有轨道信息，生成默认质子场景
    if not scenarios:
        scenarios.append(SimulationScenario(
            name="默认质子 100 MeV",
            source=ParticleSource(particle="proton", energy_MeV=100.0, direction=(0, 0, -1)),
            num_events=100000,
            physics_list="QGSP_BIC",
        ))

    return scenarios


def _pick_energy_points(energy_range: list, n: int = 3) -> list[float]:
    """在能量范围内选取 n 个等对数间隔的能量点"""
    if len(energy_range) < 2:
        return [float(energy_range[0])] if energy_range else [100.0]
    lo, hi = float(energy_range[0]), float(energy_range[1])
    if lo <= 0:
        lo = 0.1
    if n == 1:
        return [round((lo * hi) ** 0.5, 2)]
    log_lo, log_hi = math.log10(lo), math.log10(hi)
    return [round(10 ** (log_lo + i * (log_hi - log_lo) / (n - 1)), 2) for i in range(n)]
