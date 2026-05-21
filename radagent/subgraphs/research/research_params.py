"""子图节点: Web 搜索 + SpacePy 查询轨道辐射环境和材料属性，填充仿真场景"""

import math
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.schemas import ParticleSource, SimulationScenario
from radagent.tools.knowledge import recommend_physics, try_lookup_particle
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
    """查询轨道辐射环境 + 生成仿真场景（优先使用用户指定的场景）"""
    log_node_entry(_NODE, state)

    geometry = state.get("geometry")
    orbit = state.get("orbit")
    intent = state.get("intent_data", {})
    gate_feedback = state.get("gate_feedback", "")

    if not geometry:
        log_error(_NODE, "缺少屏蔽几何信息")
        update = {"parse_error": "缺少屏蔽几何信息"}
        log_node_exit(_NODE, "confirm_params", update)
        return Command(update=update, goto="confirm_params")

    # 检测 gate feedback：如果有，优先根据 feedback 修正场景
    if gate_feedback:
        log_info(_NODE, f"检测到 gate feedback，将用于改进场景生成")

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

    # 3. 生成场景：gate feedback 修正 > 用户指定 > 自动生成
    if gate_feedback:
        scenarios = _improve_scenarios_from_gate(gate_feedback, orbit, orbit_env, geometry)
        log_info(_NODE, f"根据 gate feedback 生成 {len(scenarios)} 个场景:")
    else:
        user_scenarios = intent.get("scenarios")
        if user_scenarios:
            scenarios = _build_user_scenarios(user_scenarios)
            log_info(_NODE, f"使用用户指定的 {len(scenarios)} 个场景:")
        else:
            scenarios = _generate_scenarios(orbit, orbit_env, geometry)
            log_info(_NODE, f"自动生成 {len(scenarios)} 个场景:")

    for s in scenarios:
        epn = s.source.energy_per_nucleon_MeV
        e_str = f"{epn} MeV/n" if epn else f"{s.source.energy_MeV} MeV"
        log_info(_NODE, f"  {s.name}: {s.source.particle} {e_str}, "
                  f"{s.num_events} events, {s.physics_list}")

    update = {
        "scenarios": scenarios,
        "orbit_env_data": orbit_env,
        "search_results": search_results,
        "parse_error": "",
        "gate_feedback": "",
    }
    log_node_exit(_NODE, "confirm_params", update)
    return Command(update=update, goto="confirm_params")


def _build_user_scenarios(user_scenarios: list[dict]) -> list[SimulationScenario]:
    """从用户指定的场景列表构建 SimulationScenario"""
    from radagent.tools.knowledge import try_lookup_particle

    scenarios = []
    for us in user_scenarios:
        raw_particle = us.get("particle", "proton")
        particle = try_lookup_particle(raw_particle) or raw_particle

        energy_per_nuc = us.get("energy_per_nucleon_MeV")
        energy_total = us.get("energy_MeV")
        energy_spectrum = us.get("energy_spectrum_MeV") or us.get("energy_spectrum")
        spectrum_probs = us.get("spectrum_probabilities")

        spectrum_tuple = None
        probs_tuple = None

        # 能谱模式：用能谱中最大能量作为 physics 推荐参考
        if energy_spectrum:
            spectrum_tuple = tuple(float(e) for e in energy_spectrum)
            probs_tuple = tuple(float(p) for p in spectrum_probs) if spectrum_probs else None
            ref_energy = max(spectrum_tuple) if spectrum_tuple else 100.0
            energy_total = ref_energy  # 备用单能值
        elif energy_per_nuc and not energy_total:
            mass_number = _ion_mass_number(particle)
            if mass_number:
                energy_total = energy_per_nuc * mass_number
                log_info("research_params", f"离子能量: {energy_per_nuc} MeV/n × A={mass_number} = {energy_total} MeV")
            else:
                energy_total = energy_per_nuc

        num_events = us.get("num_events", 100000)
        physics = recommend_physics(particle, energy_total or 100)
        source_type = us.get("source_type", "parallel_beam")

        scenarios.append(SimulationScenario(
            name=us.get("name", f"{particle} {energy_per_nuc or energy_total} MeV"),
            source=ParticleSource(
                particle=particle,
                energy_MeV=energy_total,
                energy_per_nucleon_MeV=energy_per_nuc,
                energy_spectrum=spectrum_tuple,
                spectrum_probabilities=probs_tuple,
                source_type=source_type,
                direction=(0, 0, -1),
            ),
            num_events=int(num_events),
            physics_list=physics,
        ))

    return scenarios


def _ion_mass_number(particle_name: str) -> int | None:
    """从粒子名获取质量数 A"""
    from radagent.tools.knowledge import CUSTOM_PARTICLES
    if particle_name in CUSTOM_PARTICLES:
        return CUSTOM_PARTICLES[particle_name].get("A")
    return None


def _improve_scenarios_from_gate(
    gate_feedback: str,
    orbit,
    orbit_env: dict,
    geometry,
) -> list[SimulationScenario]:
    """根据 gate feedback 中的建议改进场景生成。先从 feedback 中提取建议，
    如果包含场景相关建议就用 LLM 生成新场景，否则用默认自动生成。"""
    # 提取 gate feedback 中的 USER_FEEDBACK 部分
    user_fb = ""
    if "[USER_FEEDBACK]" in gate_feedback:
        user_fb = gate_feedback.split("[USER_FEEDBACK]", 1)[-1].strip()

    # 提取改进建议
    suggestions = []
    for line in gate_feedback.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            suggestions.append(line[2:])

    log_info("research_params", f"Gate suggestions: {suggestions[:3]}")
    if user_fb:
        log_info("research_params", f"User feedback: {user_fb[:200]}")

    # 如果用户在 gate feedback 中提供了具体的场景描述，用 LLM 解析
    if user_fb and llm:
        from radagent.tools.knowledge import CUSTOM_PARTICLES
        prompt = f"""根据以下反馈和改进建议，生成完整的仿真场景列表。

轨道: {orbit.orbit_name if orbit else '未知'} ({orbit.altitude_km if orbit else 0} km)
屏蔽结构: {geometry.name}, {len(geometry.layers)} 层
改进建议: {"; ".join(suggestions)}
用户反馈: {user_fb}

返回 JSON 数组（不要其他内容）:
[
    {{"name": "场景名", "particle": "粒子名", "energy_per_nucleon_MeV": 核子能量或null, "energy_MeV": 总能量或null, "num_events": 事件数, "physics_list": "auto"}}
]"""

        try:
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            import json
            parsed = json.loads(content)
            if isinstance(parsed, list) and parsed:
                scenarios = []
                for i, item in enumerate(parsed):
                    raw_particle = item.get("particle", "proton")
                    particle = try_lookup_particle(raw_particle) or raw_particle
                    energy_per_nuc = item.get("energy_per_nucleon_MeV")
                    energy_total = item.get("energy_MeV")
                    num_events = item.get("num_events", 100000)
                    physics = item.get("physics_list", "auto")

                    if energy_per_nuc and not energy_total:
                        ion_info = CUSTOM_PARTICLES.get(particle)
                        if ion_info:
                            energy_total = energy_per_nuc * ion_info["A"]
                        else:
                            energy_total = energy_per_nuc

                    if not energy_total:
                        energy_total = 100.0

                    if physics == "auto":
                        physics = recommend_physics(particle, energy_total)

                    scenarios.append(SimulationScenario(
                        name=item.get("name", f"场景{chr(65+i)}"),
                        source=ParticleSource(
                            particle=particle,
                            energy_MeV=energy_total,
                            energy_per_nucleon_MeV=energy_per_nuc,
                            direction=(0, 0, -1),
                        ),
                        num_events=int(num_events),
                        physics_list=physics,
                    ))
                log_info("research_params", f"LLM 根据 feedback 生成 {len(scenarios)} 个场景")
                return scenarios
        except Exception as e:
            log_error("research_params", f"LLM 场景改进失败: {e}")

    # 降级：根据 gate suggestions 自动生成更完善的场景
    return _generate_scenarios(orbit, orbit_env, geometry)


def _generate_scenarios(orbit, orbit_env: dict, geometry) -> list[SimulationScenario]:
    """根据轨道环境生成默认仿真场景"""
    # 深空轨道 → GCR 智能源配置（能谱 + 各向同性 + 重离子）
    if orbit and orbit.orbit_name == "深空":
        return _generate_gcr_scenarios(orbit)

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


def _generate_gcr_scenarios(orbit) -> list[SimulationScenario]:
    """为深空 GCR 环境生成合理场景：质子能谱 + 典型重离子 + 各向同性源"""
    scenarios = []

    # 质子 GCR 能谱 (简化 1/E 分布, 10 MeV - 10 GeV)
    proton_energies = (10, 30, 100, 300, 1000, 3000, 10000)
    proton_probs = tuple(1.0 / e for e in proton_energies)  # ~1/E 权重
    scenarios.append(SimulationScenario(
        name="GCR 质子能谱",
        source=ParticleSource(
            particle="proton",
            energy_MeV=300.0,  # 中值能量（备用）
            energy_spectrum=proton_energies,
            spectrum_probabilities=proton_probs,
            source_type="isotropic",
            direction=(0, 0, -1),
        ),
        num_events=500000,
        physics_list="QGSP_BERT",
    ))

    # α 粒子 GCR 能谱
    alpha_energies = (10, 50, 200, 500, 2000, 5000)
    alpha_probs = tuple(0.3 / e for e in alpha_energies)
    scenarios.append(SimulationScenario(
        name="GCR α粒子能谱",
        source=ParticleSource(
            particle="alpha",
            energy_MeV=200.0,
            energy_spectrum=alpha_energies,
            spectrum_probabilities=alpha_probs,
            source_type="isotropic",
            direction=(0, 0, -1),
        ),
        num_events=200000,
        physics_list="QGSP_BIC",
    ))

    # 典型 GCR 重离子（单能典型值 + 各向同性）
    gcr_ions = [
        ("C_ion", 400, 12, "碳离子 C-12"),
        ("O_ion", 600, 16, "氧离子 O-16"),
        ("Si_ion", 1000, 28, "硅离子 Si-28"),
        ("Fe_ion", 1000, 56, "铁离子 Fe-56"),
    ]
    for ion_name, epn, a, desc in gcr_ions:
        energy_total = epn * a
        scenarios.append(SimulationScenario(
            name=f"GCR {desc} {epn} MeV/n",
            source=ParticleSource(
                particle=ion_name,
                energy_MeV=float(energy_total),
                energy_per_nucleon_MeV=float(epn),
                source_type="isotropic",
                direction=(0, 0, -1),
            ),
            num_events=100000,
            physics_list="FTFP_BERT",
        ))

    log_info("research_params", f"GCR 场景: {len(scenarios)} 个 (质子能谱+α能谱+4种重离子)")
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
