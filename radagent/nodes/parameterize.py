"""节点: 将 SimulationPlan 渲染为多层 Geant4 C++ 工程（确定性，无 LLM）"""

from typing import Literal

from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.state import RadAgentState
from radagent.schemas import BuildResult
from radagent.tools.geant4_tools import render_multilayer_template

_NODE = "parameterize"


def parameterize(state: RadAgentState) -> Command[Literal["research", "build_and_run"]]:
    """遍历 SimulationPlan 中的每个场景，渲染 Geant4 模板"""
    log_node_entry(_NODE, state)

    plan = state.get("sim_plan")
    if not plan or not plan.scenarios:
        log_error(_NODE, "缺少仿真计划或场景为空，返回调研阶段")
        return Command(
            update={"parse_error": "缺少仿真计划或场景为空"},
            goto="research",
        )

    geometry = plan.geometry
    scenarios = plan.scenarios

    # 用第一个场景渲染模板（后续场景可复用同一源码，只改 macro）
    primary_scenario = scenarios[0]

    source_dir, files = render_multilayer_template(geometry, primary_scenario)

    layer_info = ", ".join(f"{l.name}({l.geant4_material} {l.thickness_mm}mm)" for l in geometry.layers)
    log_info(_NODE, f"模板渲染完成: {source_dir}")
    log_info(_NODE, f"结构: {geometry.name} [{layer_info}]")
    log_info(_NODE, f"场景数: {len(scenarios)}, 首个场景: {primary_scenario.name} "
              f"({primary_scenario.source.particle} {primary_scenario.source.energy_MeV} MeV, "
              f"{primary_scenario.num_events} events)")
    log_info(_NODE, f"生成文件: {list(files.keys())}")

    update = {
        "build": BuildResult(source_dir=source_dir),
        "parse_error": "",
    }
    log_node_exit(_NODE, "build_and_run", update)

    return Command(update=update, goto="build_and_run")
