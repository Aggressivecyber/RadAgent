"""Mermaid diagram renderer for RadAgent graph topology.

Generates human-readable Mermaid flowcharts from the static graph structure.
No runtime dependency on LangGraph — all topology is declared here as data.

Design: topology as data → renderer as pure function → output as string.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ─── Color palette ───────────────────────────────────────────────────

_FILL = {
    "workspace": "#E8F5E9",  # green tint — bootstrap
    "io": "#FFF3E0",  # orange tint — I/O adapters
    "core": "#E3F2FD",  # blue tint — core modeling
    "guard": "#FCE4EC",  # pink tint — gate/guard
    "codegen": "#F3E5F5",  # purple tint — code generation
    "gate": "#FFF9C4",  # yellow tint — validation gates
    "artifact": "#E0F7FA",  # cyan tint — artifact/report
    "subgraph": "#F5F5F5",  # grey — subgraph wrapper
    "end": "#FFCDD2",  # red tint — terminal
}

_BORDER = {
    "workspace": "#388E3C",
    "io": "#F57C00",
    "core": "#1976D2",
    "guard": "#C62828",
    "codegen": "#7B1FA2",
    "gate": "#F9A825",
    "artifact": "#00838F",
    "subgraph": "#757575",
    "end": "#D32F2F",
}


# ─── Data model ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class EdgeSpec:
    """A directed edge between two nodes."""

    source: str
    target: str
    label: str = ""
    style: str = ""  # "retry" | "block" | ""


@dataclass(frozen=True)
class NodeSpec:
    """A node in a graph."""

    node_id: str
    label: str
    kind: str = "core"  # workspace | io | core | guard | codegen | gate | artifact | subgraph | end
    is_entry: bool = False


@dataclass(frozen=True)
class SubgraphSpec:
    """Complete specification of a (sub)graph."""

    name: str
    display_name: str
    description: str
    nodes: tuple[NodeSpec, ...]
    edges: tuple[EdgeSpec, ...]
    conditional_edges: tuple[EdgeSpec, ...] = ()


# ─── Graph topology declarations ─────────────────────────────────────
# All topology is declared as static data.  When graph code changes,
# update these declarations to keep diagrams in sync.


def get_main_graph_spec() -> SubgraphSpec:
    """Main orchestration graph — 13 nodes, conditional routing."""
    return SubgraphSpec(
        name="main_graph",
        display_name="RadAgent Main Graph",
        description="主调度图 — 仅负责子图调度，不含领域逻辑",
        nodes=(
            NodeSpec("initialize_request", "初始化请求", "io", is_entry=True),
            NodeSpec("intent_router", "意图路由", "guard"),
            NodeSpec("chat_response_node", "聊天响应", "artifact"),
            NodeSpec("prepare_workspace", "准备工作区", "workspace"),
            NodeSpec("context_subgraph", "Context 子图", "subgraph"),
            NodeSpec("task_planning_subgraph", "任务规划 子图", "subgraph"),
            NodeSpec("g4_modeling_subgraph", "G4 建模 子图", "subgraph"),
            NodeSpec("human_confirmation_subgraph", "Human Confirmation 子图", "subgraph"),
            NodeSpec("g4_codegen_subgraph", "G4 代码生成 子图", "subgraph"),
            NodeSpec("patch_subgraph", "Patch 子图", "subgraph"),
            NodeSpec("gate_subgraph", "门禁验证 子图", "subgraph"),
            NodeSpec("artifact_subgraph", "产物收集 子图", "subgraph"),
            NodeSpec("report_subgraph", "报告生成 子图", "subgraph"),
        ),
        edges=(
            EdgeSpec("initialize_request", "intent_router"),
            EdgeSpec("chat_response_node", "END"),
            EdgeSpec("prepare_workspace", "context_subgraph"),
            EdgeSpec("report_subgraph", "END"),
        ),
        conditional_edges=(
            EdgeSpec("intent_router", "chat_response_node", "chat"),
            EdgeSpec("intent_router", "human_confirmation_subgraph", "确认回复"),
            EdgeSpec("intent_router", "prepare_workspace", "simulation_work"),
            EdgeSpec("context_subgraph", "task_planning_subgraph", "充分 → 规划"),
            EdgeSpec("context_subgraph", "report_subgraph", "不足 → 报告", "block"),
            EdgeSpec("task_planning_subgraph", "g4_modeling_subgraph", "scope=geant4"),
            EdgeSpec("task_planning_subgraph", "report_subgraph", "TCAD/SPICE/失败", "block"),
            EdgeSpec("g4_modeling_subgraph", "human_confirmation_subgraph", "需确认"),
            EdgeSpec("g4_modeling_subgraph", "g4_codegen_subgraph", "通过且无需确认"),
            EdgeSpec("g4_modeling_subgraph", "report_subgraph", "失败", "block"),
            EdgeSpec("human_confirmation_subgraph", "g4_codegen_subgraph", "确认完成"),
            EdgeSpec("human_confirmation_subgraph", "context_subgraph", "补充信息", "retry"),
            EdgeSpec("human_confirmation_subgraph", "report_subgraph", "拒绝/失败/待输入", "block"),
            EdgeSpec("g4_codegen_subgraph", "patch_subgraph", "通过"),
            EdgeSpec("g4_codegen_subgraph", "report_subgraph", "失败", "block"),
            EdgeSpec("patch_subgraph", "gate_subgraph", "已应用"),
            EdgeSpec("patch_subgraph", "report_subgraph", "失败", "block"),
            EdgeSpec("gate_subgraph", "artifact_subgraph", "passed"),
            EdgeSpec("gate_subgraph", "context_subgraph", "Gate 0 失败", "retry"),
            EdgeSpec("gate_subgraph", "task_planning_subgraph", "Gate 1 失败", "retry"),
            EdgeSpec("gate_subgraph", "g4_modeling_subgraph", "Gate 2/G4-A~E 失败", "retry"),
            EdgeSpec("gate_subgraph", "human_confirmation_subgraph", "G4-H 失败", "retry"),
            EdgeSpec("gate_subgraph", "g4_codegen_subgraph", "Gate 5~9/11/G4-F~G 失败", "retry"),
            EdgeSpec("gate_subgraph", "patch_subgraph", "Gate 3~4 失败", "retry"),
            EdgeSpec("gate_subgraph", "report_subgraph", "retry≥5 或其他", "block"),
            EdgeSpec("artifact_subgraph", "report_subgraph", ""),
        ),
    )


def get_context_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="context_subgraph",
        display_name="Context 子图",
        description="RAG + Web 上下文收集与证据评分 (6 nodes)",
        nodes=(
            NodeSpec("route_sources", "路由源选择", "io", is_entry=True),
            NodeSpec("retrieve_rag_context", "RAG 上下文检索", "core"),
            NodeSpec("score_rag_context", "RAG 评分", "guard"),
            NodeSpec("retrieve_web_context", "Web 补充检索", "core"),
            NodeSpec("score_combined_context", "综合评分", "guard"),
            NodeSpec("save_evidence_map", "保存证据映射", "io"),
        ),
        edges=(
            EdgeSpec("route_sources", "retrieve_rag_context"),
            EdgeSpec("retrieve_rag_context", "score_rag_context"),
            EdgeSpec("retrieve_web_context", "score_combined_context"),
            EdgeSpec("score_combined_context", "save_evidence_map"),
            EdgeSpec("save_evidence_map", "END"),
        ),
        conditional_edges=(
            EdgeSpec("score_rag_context", "retrieve_web_context", "需 Web 补充"),
            EdgeSpec("score_rag_context", "save_evidence_map", "RAG 充分"),
        ),
    )


def get_task_planning_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="task_planning_subgraph",
        display_name="Task Planning 子图",
        description="解析用户需求 → 任务规格 (3 nodes, 含重试)",
        nodes=(
            NodeSpec("parse_task", "解析任务", "core", is_entry=True),
            NodeSpec("validate_task_spec", "验证任务规格", "guard"),
            NodeSpec("save_task_spec", "保存任务规格", "io"),
        ),
        edges=(
            EdgeSpec("parse_task", "validate_task_spec"),
            EdgeSpec("save_task_spec", "END"),
        ),
        conditional_edges=(
            EdgeSpec("validate_task_spec", "save_task_spec", "无错误"),
            EdgeSpec("validate_task_spec", "parse_task", "有错误 → 重试", "retry"),
        ),
    )


def get_g4_modeling_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="g4_modeling_subgraph",
        display_name="G4 Modeling 子图",
        description="Model IR 构建 — 核心建模管线 (14 nodes)",
        nodes=(
            NodeSpec("load_task_spec", "加载任务规格", "io", is_entry=True),
            NodeSpec("requirement_capture_node", "需求捕获", "core"),
            NodeSpec("evidence_retrieval_node", "证据检索", "core"),
            NodeSpec("model_scope_guard_node", "Scope Guard", "guard"),
            NodeSpec("geometry_decomposition_node", "几何分解", "core"),
            NodeSpec("coordinate_system_node", "坐标系定义", "core"),
            NodeSpec("material_definition_node", "材料定义", "core"),
            NodeSpec("source_definition_node", "源定义", "core"),
            NodeSpec("physics_list_node", "物理列表", "core"),
            NodeSpec("sensitive_detector_node", "灵敏探测器", "core"),
            NodeSpec("scoring_design_node", "Scoring 设计", "core"),
            NodeSpec("model_ir_validation_node", "Model IR 校验", "guard"),
            NodeSpec("model_review_report_node", "模型审查报告", "artifact"),
            NodeSpec("persist_model_ir", "持久化 Model IR", "io"),
        ),
        edges=(
            EdgeSpec("load_task_spec", "requirement_capture_node"),
            EdgeSpec("requirement_capture_node", "evidence_retrieval_node"),
            EdgeSpec("evidence_retrieval_node", "model_scope_guard_node"),
            EdgeSpec("geometry_decomposition_node", "coordinate_system_node"),
            EdgeSpec("coordinate_system_node", "material_definition_node"),
            EdgeSpec("material_definition_node", "source_definition_node"),
            EdgeSpec("source_definition_node", "physics_list_node"),
            EdgeSpec("physics_list_node", "sensitive_detector_node"),
            EdgeSpec("sensitive_detector_node", "scoring_design_node"),
            EdgeSpec("scoring_design_node", "model_ir_validation_node"),
            EdgeSpec("model_review_report_node", "persist_model_ir"),
            EdgeSpec("persist_model_ir", "END"),
        ),
        conditional_edges=(
            EdgeSpec("model_scope_guard_node", "geometry_decomposition_node", "proceed"),
            EdgeSpec("model_scope_guard_node", "persist_model_ir", "block → 失败", "block"),
            EdgeSpec("model_ir_validation_node", "model_review_report_node", "通过"),
            EdgeSpec(
                "model_ir_validation_node",
                "geometry_decomposition_node",
                "错误 < 3 → 重试",
                "retry",
            ),
            EdgeSpec("model_ir_validation_node", "persist_model_ir", "错误 ≥ 3 → 失败", "block"),
        ),
    )


def get_g4_codegen_subgraph_spec() -> SubgraphSpec:
    """G4 Codegen subgraph — coarse module agents plus final integration."""
    nodes = [
        NodeSpec("load_model_ir", "加载 Model IR", "io", is_entry=True),
        NodeSpec("build_codegen_plan", "代码生成规划", "codegen"),
        NodeSpec("plan_geometry_strategy", "几何策略规划", "codegen"),
        NodeSpec("plan_code_architecture", "架构规划", "codegen"),
        NodeSpec("build_module_contracts", "模块契约", "codegen"),
        NodeSpec("build_module_contexts", "模块上下文", "codegen"),
        NodeSpec("run_core_modules", "生成核心模块", "codegen"),
        NodeSpec("core_modules_gate", "核心层一致性", "guard"),
        NodeSpec("coordinate_core_modules_context", "协调核心上下文", "codegen"),
        NodeSpec("run_runtime_modules", "生成运行模块", "codegen"),
        NodeSpec("runtime_modules_gate", "运行层一致性", "guard"),
        NodeSpec("coordinate_runtime_modules_context", "协调运行上下文", "codegen"),
        NodeSpec("build_interface_contracts", "接口契约", "codegen"),
        NodeSpec("integration_assembler", "集成组装", "codegen"),
        NodeSpec("global_integration_agent", "最终集成 Agent", "codegen"),
        NodeSpec("runtime_execution_audit", "运行真实性审核", "guard"),
        NodeSpec("physics_quality_review", "物理质量审核", "guard"),
        NodeSpec("persist_codegen_output", "持久化输出", "io"),
    ]

    edges = [
        EdgeSpec("load_model_ir", "build_codegen_plan"),
        EdgeSpec("build_codegen_plan", "plan_geometry_strategy"),
        EdgeSpec("plan_geometry_strategy", "plan_code_architecture"),
        EdgeSpec("plan_code_architecture", "build_module_contracts"),
        EdgeSpec("build_module_contracts", "build_module_contexts"),
        EdgeSpec("build_module_contexts", "run_core_modules"),
        EdgeSpec("run_core_modules", "core_modules_gate"),
        EdgeSpec("coordinate_core_modules_context", "run_runtime_modules"),
        EdgeSpec("run_runtime_modules", "runtime_modules_gate"),
        EdgeSpec("coordinate_runtime_modules_context", "build_interface_contracts"),
        EdgeSpec("build_interface_contracts", "integration_assembler"),
        EdgeSpec("integration_assembler", "global_integration_agent"),
        EdgeSpec("global_integration_agent", "runtime_execution_audit"),
        EdgeSpec("physics_quality_review", "persist_codegen_output"),
        EdgeSpec("persist_codegen_output", "END"),
    ]

    conditional_edges = (
        EdgeSpec("core_modules_gate", "coordinate_core_modules_context", "通过"),
        EdgeSpec("core_modules_gate", "persist_codegen_output", "失败", "block"),
        EdgeSpec("runtime_modules_gate", "coordinate_runtime_modules_context", "通过"),
        EdgeSpec("runtime_modules_gate", "persist_codegen_output", "失败", "block"),
        EdgeSpec("runtime_execution_audit", "physics_quality_review", "通过"),
        EdgeSpec("runtime_execution_audit", "persist_codegen_output", "失败", "block"),
    )

    return SubgraphSpec(
        name="g4_codegen_subgraph",
        display_name="G4 Codegen 子图",
        description="粗粒度 Agent 代码生成流水线 (2 层模块 + 最终集成 + 运行/物理审核)",
        nodes=tuple(nodes),
        edges=tuple(edges),
        conditional_edges=conditional_edges,
    )


def get_human_confirmation_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="human_confirmation_subgraph",
        display_name="Human Confirmation 子图",
        description="多轮人工确认模型假设 (6 nodes)",
        nodes=(
            NodeSpec(
                "build_proposed_model_completion",
                "构建待确认模型",
                "core",
                is_entry=True,
            ),
            NodeSpec("generate_confirmation_request", "生成确认请求", "artifact"),
            NodeSpec("human_interrupt_node", "等待人工输入", "guard"),
            NodeSpec("parse_confirmation_response", "解析确认回复", "core"),
            NodeSpec("merge_user_confirmation", "合并确认结果", "core"),
            NodeSpec("validate_confirmation_completeness", "校验确认完整性", "guard"),
        ),
        edges=(
            EdgeSpec("build_proposed_model_completion", "generate_confirmation_request"),
            EdgeSpec("generate_confirmation_request", "human_interrupt_node"),
            EdgeSpec("parse_confirmation_response", "merge_user_confirmation"),
        ),
        conditional_edges=(
            EdgeSpec("human_interrupt_node", "parse_confirmation_response", "已回复"),
            EdgeSpec("human_interrupt_node", "END", "待回复", "block"),
            EdgeSpec("merge_user_confirmation", "generate_confirmation_request", "ask_more"),
            EdgeSpec(
                "merge_user_confirmation",
                "validate_confirmation_completeness",
                "approved/edited/pending",
            ),
            EdgeSpec("merge_user_confirmation", "END", "rejected/failed", "block"),
            EdgeSpec(
                "validate_confirmation_completeness",
                "generate_confirmation_request",
                "仍待确认",
                "retry",
            ),
            EdgeSpec("validate_confirmation_completeness", "END", "完成"),
        ),
    )


def get_gate_validation_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="gate_validation_subgraph",
        display_name="Gate Validation 子图",
        description="21 道门禁检查 (6 nodes, 线性)",
        nodes=(
            NodeSpec("load_gate_inputs", "加载门禁输入", "io", is_entry=True),
            NodeSpec("run_base_gates", "基础门禁 0-11", "gate"),
            NodeSpec("run_g4_modeling_gates", "G4 门禁 A-H", "gate"),
            NodeSpec("run_credibility_gate", "可信度门禁 20", "gate"),
            NodeSpec("run_visual_review_gate", "可视化验收 21", "gate"),
            NodeSpec("finalize_gate_results", "汇总结果", "gate"),
        ),
        edges=(
            EdgeSpec("load_gate_inputs", "run_base_gates"),
            EdgeSpec("run_base_gates", "run_g4_modeling_gates"),
            EdgeSpec("run_g4_modeling_gates", "run_credibility_gate"),
            EdgeSpec("run_credibility_gate", "run_visual_review_gate"),
            EdgeSpec("run_visual_review_gate", "finalize_gate_results"),
            EdgeSpec("finalize_gate_results", "END"),
        ),
    )


def get_patch_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="patch_subgraph",
        display_name="Patch 子图",
        description="Patch 审查 + 应用 (3 nodes, 线性)",
        nodes=(
            NodeSpec("load_proposed_patch", "加载 Patch", "io", is_entry=True),
            NodeSpec("review_patch", "审查 Patch", "guard"),
            NodeSpec("apply_patch", "应用 Patch", "core"),
        ),
        edges=(
            EdgeSpec("load_proposed_patch", "review_patch"),
            EdgeSpec("review_patch", "apply_patch"),
            EdgeSpec("apply_patch", "END"),
        ),
    )


def get_artifact_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="artifact_subgraph",
        display_name="Artifact 子图",
        description="GitHub-reviewable 产物收集 (3 nodes, 线性)",
        nodes=(
            NodeSpec("collect_artifacts", "收集产物", "artifact", is_entry=True),
            NodeSpec("generate_artifact_manifest", "生成 Manifest", "artifact"),
            NodeSpec("generate_artifact_readme", "生成 README", "artifact"),
        ),
        edges=(
            EdgeSpec("collect_artifacts", "generate_artifact_manifest"),
            EdgeSpec("generate_artifact_manifest", "generate_artifact_readme"),
            EdgeSpec("generate_artifact_readme", "END"),
        ),
    )


def get_report_subgraph_spec() -> SubgraphSpec:
    return SubgraphSpec(
        name="report_subgraph",
        display_name="Report 子图",
        description="最终报告生成 (1 node)",
        nodes=(NodeSpec("generate_final_report", "生成最终报告", "artifact", is_entry=True),),
        edges=(EdgeSpec("generate_final_report", "END"),),
    )


def get_all_subgraph_specs() -> dict[str, SubgraphSpec]:
    """Return all subgraph specifications keyed by name."""
    return {
        "context": get_context_subgraph_spec(),
        "task_planning": get_task_planning_subgraph_spec(),
        "g4_modeling": get_g4_modeling_subgraph_spec(),
        "human_confirmation": get_human_confirmation_subgraph_spec(),
        "g4_codegen": get_g4_codegen_subgraph_spec(),
        "gate_validation": get_gate_validation_subgraph_spec(),
        "patch": get_patch_subgraph_spec(),
        "artifact": get_artifact_subgraph_spec(),
        "report": get_report_subgraph_spec(),
    }


# ─── Mermaid renderer ────────────────────────────────────────────────


class MermaidRenderer:
    """Pure-function Mermaid diagram generator.

    Usage::

        renderer = MermaidRenderer()
        mermaid_str = renderer.render(get_main_graph_spec())
    """

    def __init__(self, direction: str = "TB") -> None:
        self._dir = direction

    def render(self, spec: SubgraphSpec) -> str:
        """Render a SubgraphSpec to a Mermaid flowchart string."""
        lines: list[str] = []
        lines.append(f"flowchart {self._dir}")
        lines.append("")

        # Title comment
        lines.append(f"    %% {spec.display_name}")
        lines.append(f"    %% {spec.description}")
        lines.append("")

        # Node declarations with styles
        for node in spec.nodes:
            lines.append(self._render_node(node))
        lines.append("")

        # Unconditional edges
        for edge in spec.edges:
            lines.append(self._render_edge(edge))
        if spec.edges:
            lines.append("")

        # Conditional edges
        if spec.conditional_edges:
            lines.append("    %% Conditional routes")
            for edge in spec.conditional_edges:
                lines.append(self._render_conditional_edge(edge))
            lines.append("")

        # Style definitions
        lines.extend(self._render_styles(spec.nodes))
        lines.append("")
        return "\n".join(lines)

    def render_combined(self, main_spec: SubgraphSpec, subgraphs: dict[str, SubgraphSpec]) -> str:
        """Render main graph with all subgraphs as Mermaid subgraphs."""
        lines: list[str] = []
        lines.append(f"flowchart {self._dir}")
        lines.append("")

        # Main graph nodes that are not subgraph wrappers
        main_wrapper_ids = {n.node_id for n in main_spec.nodes if n.kind == "subgraph"}
        non_wrapper_nodes = [n for n in main_spec.nodes if n.node_id not in main_wrapper_ids]

        # Declare non-wrapper main nodes
        for node in non_wrapper_nodes:
            lines.append(self._render_node(node))
        lines.append("")

        # Render each subgraph as a Mermaid subgraph block
        for sub_key, sub_spec in subgraphs.items():
            lines.append(f"    subgraph {sub_spec.name}")
            lines.append(f"        direction {self._dir}")
            for node in sub_spec.nodes:
                safe_label = node.label.replace('"', "'")
                shape_open, shape_close = self._node_shape(node.kind)
                lines.append(f'        {node.node_id}{shape_open}"{safe_label}"{shape_close}')
            for edge in sub_spec.edges:
                if edge.target == "END":
                    lines.append(f"        {edge.source} --> {sub_spec.name}_end((END))")
                else:
                    label_part = f"|{edge.label}|" if edge.label else ""
                    lines.append(f"        {edge.source} --> {label_part}{edge.target}")
            lines.append("    end")
            lines.append("")

        # Main graph edges (connecting subgraphs)
        lines.append("    %% Main graph routing")
        for edge in main_spec.edges:
            if edge.target == "END":
                lines.append(f"    {edge.source} --> END((END))")
            else:
                lines.append(f"    {edge.source} --> {edge.target}")
        lines.append("")

        for edge in main_spec.conditional_edges:
            lines.append(self._render_conditional_edge(edge, indent=4))
        lines.append("")

        # Styles
        seen_kinds: set[str] = set()
        for node in non_wrapper_nodes:
            seen_kinds.add(node.kind)
        lines.extend(self._render_style_defs(seen_kinds))
        lines.append("")
        return "\n".join(lines)

    # ── internal helpers ──

    @staticmethod
    def _node_shape(kind: str) -> tuple[str, str]:
        """Return Mermaid shape delimiters for a node kind."""
        if kind == "end":
            return "((", "))"
        if kind in ("guard", "gate"):
            return "{{", "}}"
        if kind in ("io",):
            return "[", "]"
        if kind in ("subgraph",):
            return "[", "]"
        return "(", ")"

    def _render_node(self, node: NodeSpec) -> str:
        safe_label = node.label.replace('"', "'")
        shape_open, shape_close = self._node_shape(node.kind)
        prefix = "    "
        entry_marker = " :::entry" if node.is_entry else ""
        return f'{prefix}{node.node_id}{shape_open}"{safe_label}"{shape_close}{entry_marker}'

    @staticmethod
    def _render_edge(edge: EdgeSpec) -> str:
        label_part = f"|{edge.label}|" if edge.label else ""
        if edge.target == "END":
            return f"    {edge.source} --> {label_part}END((END))"
        return f"    {edge.source} --> {label_part}{edge.target}"

    @staticmethod
    def _render_conditional_edge(edge: EdgeSpec, indent: int = 4) -> str:
        pad = " " * indent
        if edge.style == "retry":
            arrow = "-.->"
        elif edge.style == "block":
            arrow = "==>"
        else:
            arrow = "-->"
        label_part = f"|{edge.label}|" if edge.label else ""
        if edge.target == "END":
            return f"{pad}{edge.source} {arrow} {label_part}END((END))"
        return f"{pad}{edge.source} {arrow} {label_part}{edge.target}"

    def _render_styles(self, nodes: tuple[NodeSpec, ...]) -> list[str]:
        seen_kinds: set[str] = {n.kind for n in nodes}
        return self._render_style_defs(seen_kinds)

    @staticmethod
    def _render_style_defs(kinds: set[str]) -> list[str]:
        lines: list[str] = []
        lines.append("    %% Node styles")
        for kind in sorted(kinds):
            fill = _FILL.get(kind, "#FFFFFF")
            border = _BORDER.get(kind, "#000000")
            lines.append(
                f"    classDef {kind} fill:{fill},stroke:{border},stroke-width:2px,color:#333"
            )

        # Collect node IDs per kind
        return lines


# ─── Public API ──────────────────────────────────────────────────────

_renderer = MermaidRenderer()


def draw_main_graph() -> str:
    """Return Mermaid diagram of the main orchestration graph."""
    return _renderer.render(get_main_graph_spec())


def draw_subgraph(name: str) -> str:
    """Return Mermaid diagram of a specific subgraph.

    Args:
        name: Subgraph key — one of: context, task_planning, g4_modeling,
              human_confirmation, g4_codegen, gate_validation, patch, artifact, report
    """
    specs = get_all_subgraph_specs()
    if name not in specs:
        available = ", ".join(sorted(specs.keys()))
        raise ValueError(f"Unknown subgraph '{name}'. Available: {available}")
    return _renderer.render(specs[name])


def draw_all() -> dict[str, str]:
    """Return Mermaid diagrams for main graph + all subgraphs.

    Returns:
        Dict mapping graph name to Mermaid string.
        Keys: "main_graph", "context", "task_planning", ...
    """
    result: dict[str, str] = {"main_graph": draw_main_graph()}
    for name in get_all_subgraph_specs():
        result[name] = draw_subgraph(name)
    return result


def draw_combined() -> str:
    """Return a single combined Mermaid diagram with main + all subgraphs."""
    return _renderer.render_combined(
        get_main_graph_spec(),
        get_all_subgraph_specs(),
    )


def export_mermaid(
    output_dir: str | Path = ".",
    combined: bool = True,
    individual: bool = True,
) -> list[Path]:
    """Write Mermaid diagrams to .mmd files.

    Args:
        output_dir: Directory to write files into.
        combined: Whether to write the combined overview diagram.
        individual: Whether to write individual diagrams per graph.

    Returns:
        List of written file paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if combined:
        path = out / "radagent_graph_overview.mmd"
        path.write_text(draw_combined(), encoding="utf-8")
        written.append(path)

    if individual:
        for name, content in draw_all().items():
            path = out / f"{name}.mmd"
            path.write_text(content, encoding="utf-8")
            written.append(path)

    return written


# ─── CLI entry point ─────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for graph visualization."""
    import argparse

    parser = argparse.ArgumentParser(
        description="RadAgent Graph Visualizer — 生成 Mermaid 图结构图"
    )
    parser.add_argument(
        "command",
        choices=["draw", "export"],
        help="'draw' 打印到终端, 'export' 写入 .mmd 文件",
    )
    parser.add_argument(
        "--main",
        action="store_true",
        help="仅输出主图",
    )
    parser.add_argument(
        "--sub",
        type=str,
        default=None,
        help="仅输出指定子图 "
        "(context/task_planning/g4_modeling/human_confirmation/g4_codegen/"
        "gate_validation/patch/artifact/report)",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="输出合并视图 (主图 + 所有子图)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="docs/graphs",
        help="export 输出目录 (默认: docs/graphs)",
    )

    args = parser.parse_args()

    if args.command == "draw":
        if args.sub:
            print(draw_subgraph(args.sub))
        elif args.combined:
            print(draw_combined())
        elif args.main:
            print(draw_main_graph())
        else:
            # Default: print all
            for name, content in draw_all().items():
                print(f"\n{'=' * 60}")
                print(f"  {name}")
                print(f"{'=' * 60}\n")
                print(content)

    elif args.command == "export":
        paths = export_mermaid(
            output_dir=args.output,
            combined=not args.main and not args.sub,
            individual=True,
        )
        for p in paths:
            print(f"  ✅ {p}")


if __name__ == "__main__":
    main()
