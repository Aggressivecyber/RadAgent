"""节点: 检查 SimulationPlan 有效性（渲染已移至 build_and_run 并发执行）"""
from typing import Literal

from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.state import RadAgentState

_NODE = "parameterize"


def parameterize(state: RadAgentState) -> Command[Literal["research", "build_and_run"]]:
    """验证仿真计划，准备进入并发渲染/编译/运行"""
    log_node_entry(_NODE, state)

    plan = state.get("sim_plan")
    if not plan or not plan.scenarios:
        log_error(_NODE, "缺少仿真计划或场景为空，返回调研阶段")
        return Command(
            update={"parse_error": "缺少仿真计划或场景为空"},
            goto="research",
        )

    geometry = plan.geometry
    layer_info = ", ".join(f"{l.name}({l.geant4_material} {l.thickness_mm}mm)" for l in geometry.layers)
    log_info(_NODE, f"计划验证通过: {geometry.name} [{layer_info}]")
    log_info(_NODE, f"场景数: {len(plan.scenarios)}, 横截面: {geometry.size_xy_cm} cm")

    update = {"parse_error": ""}
    log_node_exit(_NODE, "build_and_run", update)
    return Command(update=update, goto="build_and_run")
