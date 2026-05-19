"""节点: 生成报告 + 人工审核 (LLM + interrupt)"""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.schemas import ControlState
from radagent.state import RadAgentState

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0.3)
except Exception:
    llm = None

REPORT_PROMPT = """你是辐照仿真报告撰写专家。根据仿真参数和结果，生成一份中文报告。

报告格式:
# 辐照仿真报告

## 1. 仿真配置
- 粒子类型与能量
- 靶材材料与尺寸
- 物理列表
- 事件数

## 2. 仿真结果
- 总能量沉积
- 每事件平均沉积
- 粒子穿透情况

## 3. 结果分析
- 物理解释
- 风险评估

## 4. 异常检测
- 检测结果

## 5. 建议
- 后续表征建议
- 注意事项

## 6. 声明
- 本报告由 RadG4-Agent 自动生成，仅供参考"""


def generate_report(state: RadAgentState) -> dict:
    """LLM 生成报告"""
    params = state["sim_params"]
    result = state.get("result")
    anomaly = state.get("anomaly", [])
    build = state.get("build")

    # 构建上下文
    result_text = f"总剂量: {result.total_dose_Gy:.4e}\n每事件: {result.dose_per_event_Gy:.4e}\n穿透: {result.penetrated}" if result else "无结果"
    anomaly_text = "\n".join(f"- {a.status}: {a.details}" for a in anomaly) if anomaly else "无异常"
    stderr_note = f"\n\n注意: 仿真有警告:\n{build.run_stderr[:500]}" if build and build.run_stderr else ""

    response = llm.invoke([
        SystemMessage(content=REPORT_PROMPT),
        HumanMessage(content=(
            f"仿真参数:\n"
            f"- 粒子: {params.particle.particle} {params.particle.energy_MeV} MeV\n"
            f"- 材料: {params.material.name} ({params.material.geant4_name}), "
            f"厚度 {params.material.thickness_um} um\n"
            f"- 物理列表: {params.physics_list}\n"
            f"- 事件数: {params.num_events}\n\n"
            f"仿真结果:\n{result_text}\n\n"
            f"异常检测:\n{anomaly_text}{stderr_note}"
        )),
    ])

    return {"report": response.content}


def human_review(state: RadAgentState) -> Command[Literal["__end__", "parse_intent"]]:
    """人工审核报告 — interrupt 暂停等待用户确认"""
    decision = interrupt({
        "message": "请审核报告",
        "report_preview": state.get("report", "")[:500],
    })

    if decision.get("approved"):
        return Command(
            update={"control": ControlState(approved=True)},
            goto="__end__",
        )
    else:
        feedback = decision.get("feedback", "请重新分析")
        return Command(
            update={
                "control": ControlState(approved=False),
                "parse_error": f"用户反馈: {feedback}",
                "user_input": feedback,
            },
            goto="parse_intent",
        )
