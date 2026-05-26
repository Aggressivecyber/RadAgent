"""门禁节点: LLM + RAG 多维度质量评估"""
from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import ControlState, GateResult
from radagent.state import RadAgentState
from radagent.tools.model_router import get_premium_llm

llm = get_premium_llm()

logger = logging.getLogger("radagent.node.tools")


# ─── 评估 prompt ─────────────────────────────────────────────

SIM_GATE_PROMPT = """你是航天辐照仿真结果审核专家。评估以下仿真构建和运行结果的多维度质量。

⚠️ **用户原始需求（最高优先级）**:
{user_input}

构建结果:
{build_data}

仿真结果:
{results_data}

仿真计划:
{plan_data}

参考知识:
{rag_context}

评估维度（每项 0-10 分，维度 1 为最高优先级）:
1. **用户需求匹配度（权重最高）**: 仿真是否实际执行了用户需求中指定的配置（材料、粒子、能量、轨道、屏蔽结构等）。如果用户要求某材料但实际未使用、要求某粒子但源配置不同，此项必须低分。此项 = 0 → 直接不通过
2. 编译状态: 是否编译成功
3. 运行状态: 是否运行完成
4. 结果有效性: 事件数是否大于0，剂量是否非零
5. 剂量合理性: 总剂量量级是否在物理合理范围（参照典型轨道辐射剂量）
6. 穿透分析: 粒子是否穿透到敏感体积，是否需要调整屏蔽

评分规则:
- 用户需求匹配度 = 0 → 不通过（无论其他分数）
- 编译状态 = 0 → 不通过
- 运行状态 = 0 → 不通过
- 总分 < 48 → 不通过

严格返回 JSON（不要其他内容）:
{{"pass": true/false, "scores": {{"用户需求匹配度": N, "编译状态": N, "运行状态": N, "结果有效性": N, "剂量合理性": N, "穿透分析": N}}, "issues": ["问题1", ...], "suggestions": ["建议1", ...]}}"""

REPORT_GATE_PROMPT = """你是仿真报告审核专家。评估以下报告的多维度质量。

⚠️ **用户原始需求（最高优先级）**:
{user_input}

报告内容（前3000字）:
{report_data}

仿真结果摘要:
{results_summary}

图表文件:
{figure_paths}

评估维度（每项 0-10 分，维度 1 为最高优先级）:
1. **用户需求匹配度（权重最高）**: 报告是否完整回应用户原始需求中提出的每项问题或关注点。如果用户关注某材料的屏蔽效果但报告未分析、用户提到特定场景但报告未覆盖，此项必须低分。此项 = 0 → 直接不通过
2. 结构完整性: 是否包含仿真配置、结果、分析、建议等必要章节
3. 数据一致性: 报告中的数值是否与仿真结果一致
4. 分析深度: 是否有物理解释和屏蔽效能分析，而非简单罗列数据
5. 图表引用: 是否引用了生成的图表

评分规则:
- 用户需求匹配度 = 0 → 不通过（无论其他分数）
- 结构完整性 = 0 → 不通过
- 总分 < 40 → 不通过

严格返回 JSON（不要其他内容）:
{{"pass": true/false, "scores": {{"用户需求匹配度": N, "结构完整性": N, "数据一致性": N, "分析深度": N, "图表引用": N}}, "issues": ["问题1", ...], "suggestions": ["建议1", ...]}}"""


# ─── 辅助函数 ─────────────────────────────────────────────────

def _strip_markdown(content: str) -> str:
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content


def _safe_serialize(obj) -> str:
    """安全序列化对象为 JSON 字符串（支持 frozen dataclass 嵌套）"""
    if obj is None:
        return "null"
    if hasattr(obj, "__dataclass_fields__"):
        fields = {}
        for k in obj.__dataclass_fields__:
            fields[k] = _to_json_safe(getattr(obj, k))
        return json.dumps(fields, ensure_ascii=False, indent=2)
    if isinstance(obj, (list, tuple)):
        return json.dumps([_to_json_safe(i) for i in obj], ensure_ascii=False, indent=2)
    return str(obj)


def _to_json_safe(obj):
    """递归转换为 JSON 安全类型"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(i) for i in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_json_safe(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return str(obj)


def _fetch_rag(query: str) -> str:
    """从 Geant4 RAG 获取参考知识"""
    try:
        from radagent.rag.search import search_geant4
        results = search_geant4(query, top_k=3)
        if not results:
            return "无相关参考知识"
        return "\n".join(f"- [{r.get('source', '')}] {r.get('content', '')}" for r in results)
    except Exception as e:
        logger.warning("RAG 检索失败: %s", e)
        return "RAG 不可用"


def _evaluate(prompt: str) -> GateResult:
    """调用 LLM 评估，返回 GateResult"""
    if not llm:
        logger.warning("LLM 不可用，门禁默认通过")
        return GateResult(gate_name="unknown", passed=True)

    response = llm.invoke([HumanMessage(content=prompt)])
    content = _strip_markdown(response.content.strip())
    log_llm_call("gate", prompt[:500], content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("门禁 LLM 输出解析失败: %s", content[:200])
        return GateResult(gate_name="unknown", passed=True)

    scores = data.get("scores", {})
    total = sum(scores.values()) if isinstance(scores, dict) else 0
    issues = tuple(data.get("issues", []))
    suggestions = tuple(data.get("suggestions", []))

    return GateResult(
        gate_name="",
        passed=bool(data.get("pass", True)),
        scores=scores,
        total_score=float(total),
        issues=issues,
        suggestions=suggestions,
    )


def _gate_fail(
    gate_name: str,
    gate_result: GateResult,
    control: ControlState,
) -> Command:
    """门禁失败：转到 revise 节点"""
    suggestions_text = "\n".join(f"  - {s}" for s in gate_result.suggestions)
    issues_text = "\n".join(f"  - {i}" for i in gate_result.issues)
    max_score = sum(10 for _ in gate_result.scores) if gate_result.scores else 60
    error_msg = (
        f"[{gate_name}] 评分 {gate_result.total_score:.0f}/{max_score}\n"
        f"问题:\n{issues_text}\n"
        f"改进建议:\n{suggestions_text}"
    )

    next_retry = control.retry_count + 1

    if next_retry > control.max_retries:
        log_error(gate_name, f"门禁失败且已重试 {control.max_retries} 次，跳转到报告生成")
        return Command(update={"parse_error": error_msg}, goto="generate_report")

    log_info(gate_name, f"门禁失败，转到 revise 节点 (重试 {next_retry}/{control.max_retries})")
    return Command(update={
        "parse_error": error_msg,
        "gate_feedback": error_msg,
        "gate_feedback_source": gate_name,
        "control": ControlState(
            retry_count=next_retry,
            max_retries=control.max_retries,
        ),
    }, goto="revise")


# ─── 两个门禁节点 ─────────────────────────────────────────────

def sim_gate(state: RadAgentState) -> Command[Literal["revise", "analyze"]]:
    """评估仿真构建和运行结果质量"""
    log_node_entry("sim_gate", state)

    build = state.get("build")
    results = state.get("results", [])
    plan = state.get("sim_plan")
    control = state.get("control", ControlState())

    # 序列化数据
    build_data = _safe_serialize(build) if build else "null"
    results_data = _safe_serialize(results) if results else "[]"
    plan_data = _safe_serialize(plan) if plan else "null"

    # RAG 检索：剂量量级参照
    rag_context = ""
    if plan and plan.orbit:
        particle = plan.scenarios[0].source.particle if plan.scenarios else "proton"
        rag_context = _fetch_rag(f"radiation dose {plan.orbit.orbit_name} {particle} Geant4 simulation")

    prompt = SIM_GATE_PROMPT.format(
        user_input=state.get("user_input", ""),
        build_data=build_data, results_data=results_data,
        plan_data=plan_data, rag_context=rag_context or "无",
    )
    result = _evaluate(prompt)
    result = GateResult(
        gate_name="sim_gate", passed=result.passed,
        scores=result.scores, total_score=result.total_score,
        issues=result.issues, suggestions=result.suggestions,
    )

    # L2 记忆：记录门禁评估
    sim_id = state.get("simulation_id", "")
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            _mem.append_attempt(
                simulation_id=sim_id, node="sim_gate",
                scores=result.scores, issues=list(result.issues),
                suggestions=list(result.suggestions),
            )
            _mem.close()
        except Exception as e:
            logger.warning("记忆写入失败: %s", e)

    log_info("sim_gate", f"评分: {result.total_score:.0f}/60, 通过={result.passed}")

    if result.passed:
        cmd = Command(update={"parse_error": ""}, goto="analyze")
    else:
        cmd = _gate_fail("sim_gate", result, control)

    log_node_exit("sim_gate", cmd.goto, {"passed": result.passed, "score": result.total_score})
    return cmd


def report_gate(state: RadAgentState) -> Command[Literal["revise", "human_review"]]:
    """评估报告质量"""
    log_node_entry("report_gate", state)

    report = state.get("report", "")
    results = state.get("results", [])
    figure_paths = state.get("figure_paths", {})
    control = state.get("control", ControlState())

    # 结果摘要
    results_summary = ""
    for r in results:
        results_summary += f"- {r.scenario_name}: 剂量={r.total_dose_Gy:.4e} Gy\n"

    prompt = REPORT_GATE_PROMPT.format(
        user_input=state.get("user_input", ""),
        report_data=report[:3000],
        results_summary=results_summary or "无结果",
        figure_paths=json.dumps(figure_paths, ensure_ascii=False) if figure_paths else "无",
    )
    result = _evaluate(prompt)
    result = GateResult(
        gate_name="report_gate", passed=result.passed,
        scores=result.scores, total_score=result.total_score,
        issues=result.issues, suggestions=result.suggestions,
    )

    # L2 记忆：记录门禁评估
    sim_id = state.get("simulation_id", "")
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            _mem.append_attempt(
                simulation_id=sim_id, node="report_gate",
                scores=result.scores, issues=list(result.issues),
                suggestions=list(result.suggestions),
            )
            _mem.close()
        except Exception as e:
            logger.warning("记忆写入失败: %s", e)

    log_info("report_gate", f"评分: {result.total_score:.0f}/50, 通过={result.passed}")

    if result.passed:
        cmd = Command(update={"parse_error": ""}, goto="human_review")
    else:
        cmd = _gate_fail("report_gate", result, control)

    log_node_exit("report_gate", cmd.goto, {"passed": result.passed, "score": result.total_score})
    return cmd
