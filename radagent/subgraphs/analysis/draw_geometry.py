"""分析子图节点: 绘制器件横截面示意图"""

import logging
from typing import Literal

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Patch
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.subgraphs.analysis.state import AnalysisState
from radagent.subgraphs.analysis.viz_style import (
    apply_style,
    ROLE_COLORS,
    ROLE_EDGE_COLORS,
    set_axis_grid,
    style_legend,
    wrap_label,
)

_NODE = "draw_geometry"

logger = logging.getLogger("radagent.node.tools")


def draw_geometry(state: AnalysisState) -> Command[Literal["draw_heatmap"]]:
    """绘制多层屏蔽结构横截面示意图"""
    log_node_entry(_NODE, state)
    apply_style()

    data = state.get("analysis_data", {})
    if not data:
        log_error(_NODE, "无分析数据")
        update = {"parse_error": "draw_geometry: 无分析数据"}
        log_node_exit(_NODE, "draw_heatmap", update)
        return Command(update=update, goto="draw_heatmap")

    plan = state.get("sim_plan")
    if not plan:
        log_error(_NODE, "缺少 sim_plan")
        update = {"parse_error": "draw_geometry: 缺少 sim_plan"}
        log_node_exit(_NODE, "draw_heatmap", update)
        return Command(update=update, goto="draw_heatmap")

    figures_dir = data["figures_dir"]
    layers = plan.geometry.layers
    layer_boundaries = data["layer_boundaries"]
    total_thickness = data["total_thickness_mm"]

    fig_height = 2.55 + 0.18 * max(0, len(layers) - 4)
    fig, ax = plt.subplots(figsize=(10.8, fig_height), constrained_layout=True)
    fig.suptitle(f"{plan.geometry.name}", fontsize=11, fontweight="semibold", y=1.02)

    bar_height = 0.48
    for i, layer in enumerate(layers):
        thickness = layer.thickness_mm
        x_start = layer_boundaries[i]
        color = ROLE_COLORS.get(layer.role, "#0072B2")
        edge_color = ROLE_EDGE_COLORS.get(layer.role, "#1E4E72")
        x_mid = x_start + thickness / 2

        rect = mpatches.FancyBboxPatch(
            (x_start, -bar_height / 2), thickness, bar_height,
            boxstyle="round,pad=0.01,rounding_size=0.025",
            facecolor=color, edgecolor=edge_color, linewidth=0.8, alpha=0.9,
        )
        ax.add_patch(rect)
        ax.add_patch(mpatches.Rectangle(
            (x_start, bar_height * 0.16),
            thickness,
            bar_height * 0.28,
            facecolor="white",
            edgecolor="none",
            alpha=0.10,
        ))

        density_str = f"{layer.density_g_cm3:.2f} g/cm³"
        if thickness / total_thickness >= 0.12:
            label = (
                f"{wrap_label(layer.name, width=13, max_lines=2)}\n"
                f"{wrap_label(layer.material, width=13, max_lines=1)}\n"
                f"{thickness:g} mm | {density_str}"
            )
            ax.text(x_mid, 0, label, ha="center", va="center",
                    fontsize=7.2, fontweight="semibold", linespacing=1.15)
        else:
            y_text = 0.46 if i % 2 == 0 else -0.46
            va = "bottom" if y_text > 0 else "top"
            label = f"{wrap_label(layer.name, width=12, max_lines=2)}\n{thickness:g} mm"
            ax.annotate(
                label,
                xy=(x_mid, bar_height / 2 if y_text > 0 else -bar_height / 2),
                xytext=(x_mid, y_text),
                ha="center",
                va=va,
                fontsize=6.9,
                fontweight="semibold",
                color="#263241",
                arrowprops=dict(arrowstyle="-", color="#697586", lw=0.7),
            )

    # 粒子入射方向箭头
    margin = total_thickness * 0.12
    ax.annotate("", xy=(0, 0), xytext=(-margin, 0),
                arrowprops=dict(arrowstyle="-|>", color="#B85C38", lw=1.8, mutation_scale=11))
    ax.text(-margin, bar_height * 0.9, "Incident\nbeam",
            ha="center", va="bottom", color="#B85C38", fontsize=8, fontweight="semibold")

    ax.set_xlim(-margin * 1.5, total_thickness * 1.02)
    ax.set_ylim(-0.72, 0.72)
    ax.set_xlabel("Depth from incident surface (mm)", labelpad=5)
    ax.set_title("Layer stack cross-section", loc="left", pad=7)
    ax.set_yticks([])
    set_axis_grid(ax, axis="x")
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)

    legend_elements = [
        Patch(facecolor=ROLE_COLORS["shield"], edgecolor=ROLE_EDGE_COLORS["shield"], label="屏蔽层"),
        Patch(facecolor=ROLE_COLORS["insulation"], edgecolor=ROLE_EDGE_COLORS["insulation"], label="绝热层"),
        Patch(facecolor=ROLE_COLORS["structure"], edgecolor=ROLE_EDGE_COLORS["structure"], label="结构层"),
        Patch(facecolor=ROLE_COLORS["sensitive"], edgecolor=ROLE_EDGE_COLORS["sensitive"], label="敏感体积"),
    ]
    legend = ax.legend(
        handles=legend_elements,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.24),
        ncol=min(4, len(legend_elements)),
        borderaxespad=0.0,
        columnspacing=1.2,
        handlelength=1.4,
    )
    style_legend(legend)

    fig_path = f"{figures_dir}/geometry_schematic.png"
    fig.savefig(fig_path)
    plt.close(fig)

    log_info(_NODE, f"器件示意图已保存: {fig_path}")

    fig_paths = dict(state.get("figure_paths", {}))
    fig_paths["geometry"] = fig_path

    update = {"figure_paths": fig_paths}
    log_node_exit(_NODE, "draw_heatmap", update)
    return Command(update=update, goto="draw_heatmap")
