"""分析子图节点: 绘制各层能量沉积谱"""

import logging
from string import ascii_lowercase
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.subgraphs.analysis.state import AnalysisState
from radagent.subgraphs.analysis.viz_style import (
    apply_style,
    remove_top_right_spines,
    set_axis_grid,
    wrap_label,
    MUTED_INK,
    OKABE_ITO,
)

_NODE = "draw_spectrum"

logger = logging.getLogger("radagent.node.tools")


def draw_spectrum(state: AnalysisState) -> Command[Literal["__end__"]]:
    """绘制各层能量沉积谱分布直方图"""
    log_node_entry(_NODE, state)
    apply_style()

    data = state.get("analysis_data", {})
    if not data:
        log_error(_NODE, "无分析数据")
        update = {"parse_error": "draw_spectrum: 无分析数据"}
        log_node_exit(_NODE, "__end__", update)
        return Command(update=update, goto="__end__")

    figures_dir = data["figures_dir"]
    per_layer_edeps = data["per_layer_edeps"]
    layer_names = data["layer_names"]

    n_layers = len(layer_names)
    ncols = min(3, n_layers)
    nrows = (n_layers + ncols - 1) // ncols

    all_log_edeps = []
    for name in layer_names:
        edeps_arr = np.asarray(per_layer_edeps.get(name, []), dtype=float)
        if edeps_arr.size:
            positive = edeps_arr[edeps_arr > 0]
            if positive.size:
                all_log_edeps.extend(np.log10(positive).tolist())
    shared_bins = None
    if all_log_edeps:
        lo, hi = np.percentile(all_log_edeps, [0.5, 99.8])
        if lo == hi:
            lo -= 0.5
            hi += 0.5
        shared_bins = np.linspace(lo, hi, 36)

    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(3.35 * ncols, 2.55 * nrows),
        constrained_layout=True,
    )
    fig.suptitle("Layer-wise energy deposition spectra", fontsize=10.5, fontweight="semibold", y=1.08)
    if n_layers == 1:
        axes = np.array([axes])
    elif nrows == 1:
        axes = np.array([axes])
    axes_flat = axes.flatten()

    for i, name in enumerate(layer_names):
        ax = axes_flat[i]
        panel = f"({ascii_lowercase[i]})"
        ax.text(-0.06, 1.07, panel, transform=ax.transAxes,
                fontsize=8.5, fontweight="semibold", va="top", ha="right",
                color=MUTED_INK)

        edeps = per_layer_edeps.get(name, [])

        if edeps:
            edeps_arr = np.array(edeps)
            edeps_pos = edeps_arr[edeps_arr > 0]
            if len(edeps_pos) > 0:
                log_edeps = np.log10(edeps_pos)
                bins = shared_bins if shared_bins is not None else np.linspace(log_edeps.min(), log_edeps.max(), 36)
                color = OKABE_ITO[i % len(OKABE_ITO)]
                ax.hist(log_edeps, bins=bins, color=color,
                        alpha=0.72, edgecolor="#263241", linewidth=0.35)
                ax.axvline(np.log10(edeps_pos.mean()), color="#263241", lw=0.9, alpha=0.8)
                stats_text = f"n {len(edeps_pos):,}  |  mean {edeps_pos.mean():.2e} MeV"
                ax.text(0.02, 0.93, stats_text, transform=ax.transAxes,
                        ha="left", va="top", fontsize=6.4, color=MUTED_INK,
                        bbox=dict(boxstyle="round,pad=0.24", facecolor="white",
                                  edgecolor="#D7DEE7", alpha=0.92))
            else:
                ax.text(0.5, 0.5, "No positive energy deposition",
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=9, color="gray")
        else:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, color="gray")

        ax.set_xlabel("log$_{10}$(Edep / MeV)", labelpad=4)
        ax.set_ylabel("Counts", labelpad=4)
        ax.set_title(wrap_label(name, width=18, max_lines=2), loc="left", fontsize=9, pad=7)
        if shared_bins is not None:
            ax.set_xlim(shared_bins[0], shared_bins[-1])
        ax.tick_params(axis="x", labelrotation=0)
        set_axis_grid(ax, axis="y")
        remove_top_right_spines(ax)

    for j in range(n_layers, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig_path = f"{figures_dir}/energy_spectrum.png"
    fig.savefig(fig_path)
    plt.close(fig)

    log_info(_NODE, f"能谱图已保存: {fig_path}")

    fig_paths = dict(state.get("figure_paths", {}))
    fig_paths["spectrum"] = fig_path

    update = {"figure_paths": fig_paths, "parse_error": ""}
    log_node_exit(_NODE, "__end__", update)
    return Command(update=update, goto="__end__")
