"""子图节点: 调研质量自检 — 含用户需求匹配度评估 + interrupt 人工兜底"""
from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command, interrupt

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import GateResult
from radagent.subgraphs.research.state import ResearchState
from radagent.tools.model_router import get_premium_llm

llm = get_premium_llm()

logger = logging.getLogger("radagent.node.tools")

_NODE = "research_qc"

_MAX_AUTO_RETRIES = 3

QC_PROMPT = """你是航天辐照仿真质量审核专家。评估以下仿真计划的多维度质量。

⚠️ **用户原始需求（最高优先级）**:
{user_input}

仿真计划:
{plan_data}

参考知识:
{rag_context}

评估维度（每项 0-10 分，维度 1 为最高优先级）:
1. **用户需求匹配度（权重最高）**: 仿真计划是否完整响应用户需求中的每项要求（材料、厚度、轨道、粒子类型、屏蔽结构等）。用户未明确指定的不扣分，但用户明确要求的必须落实。此项 = 0 → 直接不通过
2. 完整性: 结构、轨道、场景是否齐全
3. 物理合理性: 材料密度、厚度、能量范围是否合理
4. 材料有效性: Geant4 材料名称是否有效（G4_ 前缀且在 NIST 库中存在，或自定义材料已注册）
5. 源配置合理性: 源类型是否匹配轨道环境（深空→各向同性，LEO→平行束可接受），能谱配置是否合理
6. Geant4 可执行性: physics_list 和粒子类型 Geant4 是否支持

评分规则:
- 用户需求匹配度 = 0 → 不通过（无论其他分数）
- 任一其他维度 = 0 → 不通过
- 总分 < 48 → 不通过
- 否则 → 通过

注意:
- source_type 为 isotropic 是合理配置，不要扣分
- 能谱分布（energy_spectrum）是高级功能，不要扣分
- 深空轨道使用各向同性源是正确选择
- parallel_beam 在 LEO/MEO/GEO 也可接受
- 自定义材料（CUSTOM_MATERIALS 中注册的）是有效的
- 用户需求中未提及的部分按默认合理值处理，不因"用户没说"而扣分

严格返回 JSON（不要其他内容）:
{{"pass": true/false, "scores": {{"用户需求匹配度": N, "完整性": N, "物理合理性": N, "材料有效性": N, "源配置合理性": N, "Geant4可执行性": N}}, "issues": ["问题1", ...], "suggestions": ["建议1", ...]}}"""


def _strip_markdown(content: str) -> str:
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content


def _safe_serialize(obj) -> str:
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
    if not llm:
        logger.warning("LLM 不可用，质量检查默认通过")
        return GateResult(gate_name=_NODE, passed=True)

    response = llm.invoke([HumanMessage(content=prompt)])
    content = _strip_markdown(response.content.strip())
    log_llm_call(_NODE, prompt[:500], content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("质量检查 LLM 输出解析失败: %s", content[:200])
        return GateResult(gate_name=_NODE, passed=True)

    scores = data.get("scores", {})
    total = sum(scores.values()) if isinstance(scores, dict) else 0
    return GateResult(
        gate_name=_NODE,
        passed=bool(data.get("pass", True)),
        scores=scores,
        total_score=float(total),
        issues=tuple(data.get("issues", [])),
        suggestions=tuple(data.get("suggestions", [])),
    )


def research_qc(state: ResearchState) -> Command[Literal["revise", "research_params", "confirm_params"]]:
    """调研质量自检：用户需求匹配度 + 技术评估，自动重试失败后 interrupt 用户决策"""
    log_node_entry(_NODE, state)

    scenarios = state.get("scenarios", [])
    geometry = state.get("geometry")
    orbit = state.get("orbit")
    orbit_env = state.get("orbit_env_data", {})
    user_input = state.get("user_input", "")

    if not geometry or not scenarios:
        log_error(_NODE, "缺少几何或场景数据，直接放行")
        update = {"parse_error": ""}
        log_node_exit(_NODE, "confirm_params", update)
        return Command(update=update, goto="confirm_params")

    from radagent.schemas import SimulationPlan
    plan = SimulationPlan(
        geometry=geometry,
        orbit=orbit,
        scenarios=tuple(scenarios),
        notes=f"数据来源: {orbit_env.get('model', '未知')}",
    )
    plan_data = _safe_serialize(plan)

    rag_parts = []
    for scenario in plan.scenarios:
        if scenario.physics_list and scenario.physics_list != "auto":
            rag_parts.append(_fetch_rag(f"Geant4 physics list {scenario.physics_list}"))
    for layer in plan.geometry.layers:
        if layer.geant4_material:
            rag_parts.append(_fetch_rag(f"Geant4 material {layer.geant4_material}"))
    rag_context = "\n".join(rag_parts[:6]) if rag_parts else "无"

    prompt = QC_PROMPT.format(user_input=user_input, plan_data=plan_data, rag_context=rag_context)
    result = _evaluate(prompt)

    # L2 记忆：记录 QC 评估
    sim_id = state.get("simulation_id", "")
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            _mem.append_attempt(
                simulation_id=sim_id, node="research_qc",
                scores=result.scores, issues=list(result.issues),
                suggestions=list(result.suggestions),
            )
            _mem.close()
        except Exception as e:
            logger.warning("记忆写入失败: %s", e)

    max_score = sum(10 for _ in result.scores) if result.scores else 60
    log_info(_NODE, f"评分: {result.total_score:.0f}/{max_score}, 通过={result.passed}")

    if result.passed:
        log_info(_NODE, "质量检查通过，放行到 confirm_params")
        update = {"parse_error": "", "sim_plan": plan}
        log_node_exit(_NODE, "confirm_params", update)
        return Command(update=update, goto="confirm_params")

    # ── 不通过 ──────────────────────────────────────────────
    retry_count = state.get("qc_retry_count", 0)
    issues_text = "\n".join(f"  - {i}" for i in result.issues)
    suggestions_text = "\n".join(f"  - {s}" for s in result.suggestions)
    warning_msg = (
        f"[{_NODE}] 评分 {result.total_score:.0f}/{max_score}\n"
        f"问题:\n{issues_text}\n"
        f"改进建议:\n{suggestions_text}"
    )

    if retry_count < _MAX_AUTO_RETRIES:
        gate_fb = f"[GATE_FEEDBACK] {warning_msg}"
        log_info(_NODE, f"质量不达标，转到 revise ({retry_count + 1}/{_MAX_AUTO_RETRIES})")
        update = {"gate_feedback": gate_fb, "parse_error": "", "qc_retry_count": retry_count + 1}
        log_node_exit(_NODE, "revise", update)
        return Command(update=update, goto="revise")

    # 超过重试上限：interrupt 让用户决定
    log_info(_NODE, f"已重试 {_MAX_AUTO_RETRIES} 次仍未达标，interrupt 用户决策")
    decision = interrupt({
        "type": "gate_warning",
        "gate_name": _NODE,
        "message": f"自动重试 {_MAX_AUTO_RETRIES} 次后仍未达标\n{warning_msg}",
    })
    action = decision.get("action", "continue")

    if action == "modify":
        feedback = decision.get("feedback", "")
        gate_fb = f"[GATE_FEEDBACK] {warning_msg}"
        if feedback:
            gate_fb += f"\n[USER_FEEDBACK] {feedback}"
        log_info(_NODE, "用户选择修改，转到 revise")
        update = {"gate_feedback": gate_fb, "parse_error": "", "qc_retry_count": 0}
        log_node_exit(_NODE, "revise", update)
        return Command(update=update, goto="revise")
    elif action == "cancel":
        log_info(_NODE, "用户取消")
        update = {"parse_error": "用户取消仿真"}
        log_node_exit(_NODE, "confirm_params (取消)", update)
        return Command(update=update, goto="confirm_params")
    else:
        log_info(_NODE, "用户选择继续，带警告放行")
        update = {"parse_error": warning_msg, "sim_plan": plan, "qc_retry_count": 0}
        log_node_exit(_NODE, "confirm_params (带警告)", update)
        return Command(update=update, goto="confirm_params")
