"""节点: 生成报告 + 人工审核 (LLM + interrupt)"""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import ControlState
from radagent.state import RadAgentState

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0.3)
except Exception:
    llm = None

REPORT_PROMPT = """你是航天辐照仿真报告撰写专家。根据多层屏蔽结构的仿真参数和结果，生成一份中文报告。

报告格式:
# 航天器辐照仿真报告

## 1. 仿真配置
- 屏蔽结构（逐层材料、厚度）
- 轨道环境
- 仿真场景（粒子、能量、事件数）
- 物理列表

## 2. 可视化
- 附图列表（路径引用）

## 3. 仿真结果
- 逐场景总剂量
- 逐层能量沉积分布
- 敏感体积受辐照情况

## 4. 结果分析
- 屏蔽效能评估
- 各层衰减比
- 物理解释

## 5. 异常检测
- 检测结果

## 6. 建议
- 屏蔽优化建议
- 后续仿真方向

## 7. 声明
- 本报告由 RadG4-Agent 自动生成，仅供参考"""


def generate_report(state: RadAgentState) -> dict:
    """LLM 生成多层仿真报告"""
    log_node_entry("generate_report", state)

    plan = state.get("sim_plan")
    results = state.get("results", [])
    anomaly = state.get("anomaly", [])

    if not plan or not llm:
        log_error("generate_report", "缺少仿真计划或 LLM 不可用")
        update = {"report": "无法生成报告: 缺少仿真计划或 LLM 不可用"}
        log_node_exit("generate_report", "human_review", update)
        return update

    # 构建屏蔽结构描述
    geo = plan.geometry
    layers_desc = "\n".join(
        f"  {i + 1}. {l.name}: {l.material} ({l.geant4_material}), "
        f"厚度 {l.thickness_mm} mm, 密度 {l.density_g_cm3} g/cm3, 角色 [{l.role}]"
        for i, l in enumerate(geo.layers)
    )

    # 轨道描述
    orbit_desc = "无轨道信息"
    if plan.orbit:
        orbit_desc = f"{plan.orbit.orbit_name} ({plan.orbit.altitude_km} km, 倾角 {plan.orbit.inclination_deg} deg)"

    # 场景描述
    scenarios_desc = "\n".join(
        f"  - {s.name}: {s.source.particle} {s.source.energy_MeV} MeV, "
        f"{s.num_events} events, {s.physics_list}"
        for s in plan.scenarios
    )

    # 结果描述
    results_desc = ""
    for r in results:
        results_desc += f"\n场景: {r.scenario_name}\n"
        results_desc += f"  总剂量: {r.total_dose_Gy:.4e} Gy\n"
        results_desc += f"  每事件剂量: {r.dose_per_event_Gy:.4e} Gy\n"
        results_desc += f"  峰值层: {r.peak_layer}\n"
        if r.layer_doses:
            for layer, dose in r.layer_doses.items():
                results_desc += f"  {layer}: {dose:.4e} J\n"

    # 异常描述
    anomaly_text = "\n".join(f"- {a.status}: {a.details}" for a in anomaly) if anomaly else "无异常"

    user_prompt = (
        f"屏蔽结构:\n{layers_desc}\n\n"
        f"横截面: {geo.size_xy_cm} cm x {geo.size_xy_cm} cm\n"
        f"敏感体积: {geo.sensitive_volume}\n\n"
        f"轨道: {orbit_desc}\n\n"
        f"仿真场景:\n{scenarios_desc}\n\n"
        f"仿真结果:\n{results_desc}\n\n"
        f"可视化图表:\n{_figure_desc(state)}\n\n"
        f"异常检测:\n{anomaly_text}"
    )

    log_info("generate_report", f"调用 LLM 生成报告 ({len(scenarios_desc)} 场景, {len(results)} 结果)")

    response = llm.invoke([
        SystemMessage(content=REPORT_PROMPT),
        HumanMessage(content=user_prompt),
    ])

    log_llm_call("generate_report", user_prompt, response.content)
    log_info("generate_report", f"报告生成完成 ({len(response.content)} 字)")

    update = {"report": response.content}
    log_node_exit("generate_report", "human_review", update)
    return update


def _figure_desc(state: RadAgentState) -> str:
    """生成图表路径描述"""
    paths = state.get("figure_paths", {})
    if not paths:
        return "无"
    descs = {
        "geometry": "器件结构示意图",
        "heatmap": "能量沉积热力图 + 深度剂量曲线",
        "spectrum": "各层能量沉积谱",
    }
    lines = []
    for key, path in paths.items():
        label = descs.get(key, key)
        lines.append(f"- {label}: {path}")
    return "\n".join(lines)


def human_review(state: RadAgentState) -> Command[Literal["__end__", "research"]]:
    """人工审核报告 — interrupt 暂停等待用户确认"""
    log_node_entry("human_review", state)

    decision = interrupt({
        "message": "请审核报告",
        "report_preview": state.get("report", "")[:500],
    })

    if decision.get("approved"):
        log_info("human_review", "用户批准报告")
        update = {"control": ControlState(approved=True)}
        log_node_exit("human_review", "__end__", update)
        return Command(update=update, goto="__end__")
    else:
        feedback = decision.get("feedback", "请重新设计")
        log_info("human_review", f"用户拒绝, 反馈: {feedback}")
        update = {
            "control": ControlState(approved=False),
            "parse_error": f"用户反馈: {feedback}",
            "user_input": feedback,
        }
        log_node_exit("human_review", "research", update)
        return Command(update=update, goto="research")
