"""门禁节点: LLM + RAG 多维度质量评估"""
from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import ControlState, GateResult
from radagent.state import RadAgentState

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0)
except Exception:
    llm = None

logger = logging.getLogger("radagent.node.tools")


# ─── 评估 prompt ─────────────────────────────────────────────

RESEARCH_GATE_PROMPT = """你是航天辐照仿真质量审核专家。评估以下仿真计划的多维度质量。

仿真计划:
{plan_data}

参考知识:
{rag_context}

评估维度（每项 0-10 分）:
1. 完整性: 结构、轨道、场景是否齐全
2. 物理合理性: 材料密度、厚度、能量范围是否合理
3. 材料有效性: Geant4 材料名称是否有效（G4_ 前缀且在 NIST 库中存在）
4. 源配置合理性: 源类型是否匹配轨道环境（深空→各向同性合理，LEO→平行束可接受），能谱配置是否合理
5. Geant4 可执行性: physics_list 和粒子类型 Geant4 是否支持

评分规则:
- 任一维度 = 0 → 不通过
- 总分 < 40 → 不通过
- 否则 → 通过

注意:
- source_type 为 isotropic（各向同性）是合理配置，不要扣分
- 能谱分布（energy_spectrum）是高级功能，不要扣分
- 深空轨道使用各向同性源是正确选择
- parallel_beam（平行束）在 LEO/MEO/GEO 也可接受

严格返回 JSON（不要其他内容）:
{{"pass": true/false, "scores": {{"完整性": N, "物理合理性": N, "材料有效性": N, "源配置合理性": N, "Geant4可执行性": N}}, "issues": ["问题1", ...], "suggestions": ["建议1", ...]}}"""

SIM_GATE_PROMPT = """你是航天辐照仿真结果审核专家。评估以下仿真构建和运行结果的多维度质量。

构建结果:
{build_data}

仿真结果:
{results_data}

仿真计划:
{plan_data}

参考知识:
{rag_context}

评估维度（每项 0-10 分）:
1. 编译状态: 是否编译成功
2. 运行状态: 是否运行完成
3. 结果有效性: 事件数是否大于0，剂量是否非零
4. 剂量合理性: 总剂量量级是否在物理合理范围（参照典型轨道辐射剂量）
5. 穿透分析: 粒子是否穿透到敏感体积，是否需要调整屏蔽

评分规则:
- 编译状态 = 0 → 不通过
- 运行状态 = 0 → 不通过
- 总分 < 40 → 不通过

严格返回 JSON（不要其他内容）:
{{"pass": true/false, "scores": {{"编译状态": N, "运行状态": N, "结果有效性": N, "剂量合理性": N, "穿透分析": N}}, "issues": ["问题1", ...], "suggestions": ["建议1", ...]}}"""

REPORT_GATE_PROMPT = """你是仿真报告审核专家。评估以下报告的多维度质量。

报告内容（前3000字）:
{report_data}

仿真结果摘要:
{results_summary}

图表文件:
{figure_paths}

评估维度（每项 0-10 分）:
1. 结构完整性: 是否包含仿真配置、结果、分析、建议等必要章节
2. 数据一致性: 报告中的数值是否与仿真结果一致
3. 分析深度: 是否有物理解释和屏蔽效能分析，而非简单罗列数据
4. 图表引用: 是否引用了生成的图表

评分规则:
- 结构完整性 = 0 → 不通过
- 总分 < 30 → 不通过

严格返回 JSON（不要其他内容）:
{{"pass": true/false, "scores": {{"结构完整性": N, "数据一致性": N, "分析深度": N, "图表引用": N}}, "issues": ["问题1", ...], "suggestions": ["建议1", ...]}}"""


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
    retry_target: str,
    gate_result: GateResult,
    control: ControlState,
    force_pass: str | None = None,
) -> Command:
    """门禁失败：回退 + 改进建议

    Args:
        force_pass: 如果设置，不回退而是带警告放行到指定节点。
                    用于 research_gate（回退 research 无意义，用户输入不变）。
    """
    suggestions_text = "\n".join(f"  - {s}" for s in gate_result.suggestions)
    issues_text = "\n".join(f"  - {i}" for i in gate_result.issues)
    max_score = sum(10 for _ in gate_result.scores) if gate_result.scores else 50
    error_msg = (
        f"[{gate_name}] 评分 {gate_result.total_score:.0f}/{max_score}\n"
        f"问题:\n{issues_text}\n"
        f"改进建议:\n{suggestions_text}"
    )

    # research_gate 等无法通过重试修复的门禁，带警告放行
    if force_pass:
        log_info(gate_name, f"门禁未达标但无法自动修复，带警告放行到 {force_pass}")
        return Command(update={"parse_error": error_msg}, goto=force_pass)

    if control.retry_count < control.max_retries:
        log_info(gate_name, f"门禁失败，回退到 {retry_target} (重试 {control.retry_count + 1}/{control.max_retries})")
        return Command(update={
            "parse_error": error_msg,
            "control": ControlState(
                retry_count=control.retry_count + 1,
                max_retries=control.max_retries,
            ),
        }, goto=retry_target)
    else:
        log_error(gate_name, f"门禁失败且已重试 {control.max_retries} 次，跳转到报告生成")
        return Command(update={"parse_error": error_msg}, goto="generate_report")


# ─── 三个门禁节点 ─────────────────────────────────────────────

def research_gate(state: RadAgentState) -> Command[Literal["research", "parameterize", "generate_report"]]:
    """评估 research 子图输出的仿真计划质量"""
    log_node_entry("research_gate", state)

    plan = state.get("sim_plan")
    control = state.get("control", ControlState())

    # 快速预检：plan 不存在直接失败
    if not plan:
        log_error("research_gate", "仿真计划为空")
        result = GateResult(
            gate_name="research_gate", passed=False,
            scores={"完整性": 0}, total_score=0,
            issues=("仿真计划为空",),
            suggestions=("请重新描述需求，确保包含屏蔽结构信息",),
        )
        cmd = _gate_fail("research_gate", "research", result, control)
        log_node_exit("research_gate", cmd.goto, {"passed": False})
        return cmd

    # 序列化 plan
    plan_data = _safe_serialize(plan)

    # RAG 检索：验证 physics_list 和材料
    rag_parts = []
    for scenario in plan.scenarios:
        if scenario.physics_list and scenario.physics_list != "auto":
            rag_parts.append(_fetch_rag(f"Geant4 physics list {scenario.physics_list}"))
    for layer in plan.geometry.layers:
        if layer.geant4_material:
            rag_parts.append(_fetch_rag(f"Geant4 material {layer.geant4_material}"))
    rag_context = "\n".join(rag_parts[:6]) if rag_parts else "无"

    prompt = RESEARCH_GATE_PROMPT.format(plan_data=plan_data, rag_context=rag_context)
    result = _evaluate(prompt)
    result = GateResult(
        gate_name="research_gate", passed=result.passed,
        scores=result.scores, total_score=result.total_score,
        issues=result.issues, suggestions=result.suggestions,
    )

    log_info("research_gate", f"评分: {result.total_score:.0f}/50, 通过={result.passed}")

    if result.passed:
        cmd = Command(update={"parse_error": ""}, goto="parameterize")
    else:
        # 门禁失败：interrupt 让用户决定是继续还是修改
        max_score = sum(10 for _ in result.scores) if result.scores else 50
        issues_text = "\n".join(f"  - {i}" for i in result.issues)
        suggestions_text = "\n".join(f"  - {s}" for s in result.suggestions)
        warning_msg = (
            f"[调研门禁] 评分 {result.total_score:.0f}/{max_score}\n"
            f"问题:\n{issues_text}\n"
            f"改进建议:\n{suggestions_text}"
        )
        decision = interrupt({
            "type": "gate_warning",
            "gate_name": "research_gate",
            "message": warning_msg,
        })
        action = decision.get("action", "continue")

        if action == "modify":
            feedback = decision.get("feedback", "")
            gate_fb = f"[GATE_FEEDBACK] {warning_msg}"
            if feedback:
                gate_fb += f"\n[USER_FEEDBACK] {feedback}"
            log_info("research_gate", "用户选择修改，回退到 research")
            cmd = Command(update={"gate_feedback": gate_fb, "parse_error": ""}, goto="research")
        elif action == "cancel":
            log_info("research_gate", "用户取消，终止")
            cmd = Command(update={"parse_error": "用户取消仿真"}, goto="generate_report")
        else:
            log_info("research_gate", "用户选择继续，带警告放行到 parameterize")
            cmd = Command(update={"parse_error": warning_msg}, goto="parameterize")

    log_node_exit("research_gate", cmd.goto, {"passed": result.passed, "score": result.total_score})
    return cmd


def sim_gate(state: RadAgentState) -> Command[Literal["parameterize", "analyze"]]:
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
        build_data=build_data, results_data=results_data,
        plan_data=plan_data, rag_context=rag_context or "无",
    )
    result = _evaluate(prompt)
    result = GateResult(
        gate_name="sim_gate", passed=result.passed,
        scores=result.scores, total_score=result.total_score,
        issues=result.issues, suggestions=result.suggestions,
    )

    log_info("sim_gate", f"评分: {result.total_score:.0f}/50, 通过={result.passed}")

    if result.passed:
        cmd = Command(update={"parse_error": ""}, goto="analyze")
    else:
        cmd = _gate_fail("sim_gate", "parameterize", result, control)

    log_node_exit("sim_gate", cmd.goto, {"passed": result.passed, "score": result.total_score})
    return cmd


def report_gate(state: RadAgentState) -> Command[Literal["generate_report", "human_review"]]:
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

    log_info("report_gate", f"评分: {result.total_score:.0f}/40, 通过={result.passed}")

    if result.passed:
        cmd = Command(update={"parse_error": ""}, goto="human_review")
    else:
        cmd = _gate_fail("report_gate", "generate_report", result, control)

    log_node_exit("report_gate", cmd.goto, {"passed": result.passed, "score": result.total_score})
    return cmd
