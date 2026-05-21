"""分析子图节点: 绘制粒子能量沉积热力图"""

import logging
from typing import Literal

import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.subgraphs.analysis.state import AnalysisState
from radagent.subgraphs.analysis.viz_style import (
    apply_style,
    remove_top_right_spines,
    add_panel_label,
    set_axis_grid,
    style_legend,
    wrap_label,
    LAYER_BG_COLORS,
    MUTED_INK,
)

_NODE = "draw_heatmap"

logger = logging.getLogger("radagent.node.tools")


def draw_heatmap(state: AnalysisState) -> Command[Literal["draw_spectrum"]]:
    """绘制深度-横向位置能量沉积热力图 + 深度剂量分布曲线"""
    log_node_entry(_NODE, state)
    apply_style()

    data = state.get("analysis_data", {})
    if not data:
        log_error(_NODE, "无分析数据")
        update = {"parse_error": "draw_heatmap: 无分析数据"}
        log_node_exit(_NODE, "draw_spectrum", update)
        return Command(update=update, goto="draw_spectrum")

    figures_dir = data["figures_dir"]
    heatmap_2d = np.array(data["heatmap_2d"])
    depth_dose = data["depth_dose"]
    depth_bin_width = data["depth_bin_width"]
    num_depth_bins = data["num_depth_bins"]
    x_min = data["x_min"]
    x_max = data["x_max"]
    layer_boundaries = data["layer_boundaries"]
    total_thickness = data["total_thickness_mm"]
    layer_names = data["layer_names"]

    fig, axes = plt.subplots(
        2, 1,
        figsize=(7.4, 5.2),
        constrained_layout=True,
        gridspec_kw={"height_ratios": [2.15, 1], "hspace": 0.08},
    )
    fig.suptitle("Energy deposition across shielding depth", fontsize=10.5, fontweight="semibold", y=1.01)

    # === (a) 2D 热力图 ===
    ax1 = axes[0]
    add_panel_label(ax1, "(a)")
    if heatmap_2d.max() > 0:
        positive = heatmap_2d[heatmap_2d > 0]
        vmin = max(float(np.percentile(positive, 2)), 1e-12)
        vmax = float(np.percentile(positive, 99.7))
        im = ax1.imshow(
            heatmap_2d.T, aspect="auto", origin="lower",
            extent=[0, total_thickness, x_min, x_max],
            cmap="magma", interpolation="nearest",
            norm=LogNorm(vmin=vmin, vmax=vmax),
        )
        cb = fig.colorbar(im, ax=ax1, shrink=0.88, pad=0.012)
        cb.set_label("Edep (MeV, log scale)", fontsize=7.5, color=MUTED_INK)
        cb.ax.tick_params(labelsize=7, colors=MUTED_INK)
        cb.outline.set_edgecolor("#CBD3DD")
        cb.outline.set_linewidth(0.6)

    for boundary in layer_boundaries[1:-1]:
        ax1.axvline(x=boundary, color="white", linestyle="-",
                     linewidth=0.8, alpha=0.72)

    ax1.set_xlabel("Depth from incident surface (mm)", labelpad=4)
    ax1.set_ylabel("Transverse x (cm)", labelpad=4)
    ax1.set_title("2D energy map", loc="left", pad=7)
    ax1.set_xlim(0, total_thickness)
    ax1.set_ylim(x_min, x_max)
    ax1.grid(False)
    remove_top_right_spines(ax1)

    plan = state.get("sim_plan")
    if plan:
        for i, layer in enumerate(plan.geometry.layers):
            mid = (layer_boundaries[i] + layer_boundaries[i + 1]) / 2
            width = layer_boundaries[i + 1] - layer_boundaries[i]
            if width / total_thickness < 0.12:
                continue
            y_label = x_max - 0.08 * (x_max - x_min)
            ax1.text(
                mid, y_label, wrap_label(layer.name, width=10, max_lines=2),
                ha="center", va="top", fontsize=5.8, color="white", fontweight="semibold",
                bbox=dict(boxstyle="round,pad=0.18", facecolor="#111827", edgecolor="none", alpha=0.58),
                clip_on=True,
            )

    # === (b) 1D 深度剂量曲线 ===
    ax2 = axes[1]
    add_panel_label(ax2, "(b)")

    depth_centers = [(i + 0.5) * depth_bin_width for i in range(num_depth_bins)]
    dose_arr = np.asarray(depth_dose, dtype=float)
    ax2.plot(depth_centers, depth_dose, color="#C77C02", linewidth=1.35)
    ax2.fill_between(depth_centers, depth_dose, alpha=0.12, color="#C77C02", linewidth=0)

    for i, name in enumerate(layer_names):
        ax2.axvspan(layer_boundaries[i], layer_boundaries[i + 1],
                     alpha=0.65, color=LAYER_BG_COLORS[i % len(LAYER_BG_COLORS)],
                     label=name)

    if dose_arr.max() > 0 and np.count_nonzero(dose_arr) > 3:
        ax2.set_yscale("symlog", linthresh=max(float(dose_arr.max()) * 1e-4, 1e-9))
    ax2.set_xlabel("Depth from incident surface (mm)", labelpad=4)
    ax2.set_ylabel("Edep (MeV/bin)", labelpad=4)
    ax2.set_title("Depth-dose profile", loc="left", pad=7)
    legend = ax2.legend(
        fontsize=7,
        ncol=min(4, len(layer_names)),
        loc="upper right",
        borderaxespad=0.45,
        columnspacing=1.0,
        handlelength=1.4,
    )
    style_legend(legend)
    ax2.set_xlim(0, total_thickness)
    set_axis_grid(ax2, axis="y")
    remove_top_right_spines(ax2)

    fig_path = f"{figures_dir}/energy_heatmap.png"
    fig.savefig(fig_path)
    plt.close(fig)

    log_info(_NODE, f"热力图已保存: {fig_path}")

    fig_paths = dict(state.get("figure_paths", {}))
    fig_paths["heatmap"] = fig_path

    update = {"figure_paths": fig_paths}
    log_node_exit(_NODE, "draw_spectrum", update)
    return Command(update=update, goto="draw_spectrum")
