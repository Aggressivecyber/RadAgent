"""分析子图可视化共享风格 — 科学绘图规范"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import textwrap

# Okabe-Ito 色盲友好色板
OKABE_ITO = ['#E69F00', '#56B4E9', '#009E73', '#F0E442',
             '#0072B2', '#D55E00', '#CC79A7', '#000000']

# IEEE 风格低饱和色板（适合工程论文）
IEEE_MUTED = ['#377eb8', '#ff7f00', '#4daf4a', '#f781bf',
              '#a65628', '#984ea3', '#999999', '#e41a1c']

# 层角色色板（色盲友好）
ROLE_COLORS = {
    "shield": "#2F6F9F",
    "insulation": "#C9972F",
    "structure": "#8A8F98",
    "sensitive": "#B85C38",
}

ROLE_EDGE_COLORS = {
    "shield": "#1E4E72",
    "insulation": "#8F6B1B",
    "structure": "#5E646D",
    "sensitive": "#7F3C25",
}

# 逐层背景色（低饱和，用于 depth-dose 曲线的色带）
LAYER_BG_COLORS = [
    "#EFF5F9", "#FBF4E6", "#F4EEF8", "#ECF5EF",
    "#F8EEE9", "#EAF5F7", "#FBF8E8", "#EEF6EA",
]

INK = "#1F2933"
MUTED_INK = "#596575"
GRID = "#E8ECF1"
PANEL_BG = "#FBFCFE"


def apply_style():
    """应用科学绘图全局风格"""
    plt.rcParams.update({
        # 字体
        'font.family': 'sans-serif',
        'font.sans-serif': ['Noto Sans CJK JP', 'AR PL UMing CN', 'Arial', 'Helvetica', 'DejaVu Sans'],
        'axes.unicode_minus': False,
        'font.size': 8.5,
        'text.color': INK,
        # 坐标轴
        'axes.labelsize': 9,
        'axes.titlesize': 10,
        'axes.titleweight': 'semibold',
        'axes.labelcolor': INK,
        'axes.titlecolor': INK,
        'axes.linewidth': 0.7,
        'axes.prop_cycle': plt.cycler(color=OKABE_ITO),
        # 刻度
        'xtick.labelsize': 7.5,
        'ytick.labelsize': 7.5,
        'xtick.major.width': 0.6,
        'ytick.major.width': 0.6,
        'xtick.direction': 'in',
        'ytick.direction': 'in',
        'xtick.color': MUTED_INK,
        'ytick.color': MUTED_INK,
        # 图例
        'legend.fontsize': 7.5,
        'legend.frameon': True,
        'legend.framealpha': 0.92,
        'legend.edgecolor': '#D7DEE7',
        # 线条
        'lines.linewidth': 1.1,
        # 保存
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.08,
        'savefig.facecolor': 'white',
        # 图
        'figure.dpi': 150,
        'figure.facecolor': 'white',
        'axes.facecolor': PANEL_BG,
        'axes.grid': True,
        'grid.color': GRID,
        'grid.linewidth': 0.5,
        'grid.alpha': 0.85,
    })


def remove_top_right_spines(ax):
    """去除上方和右侧 spine"""
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color("#CBD3DD")
    ax.spines['bottom'].set_color("#CBD3DD")
    ax.spines['left'].set_linewidth(0.8)
    ax.spines['bottom'].set_linewidth(0.8)


def add_panel_label(ax, label: str, x: float = -0.12, y: float = 1.05):
    """添加面板标签 (a, b, c...)"""
    ax.text(x, y, label, transform=ax.transAxes,
            fontsize=9, fontweight='semibold', va='top', ha='right',
            color=MUTED_INK)


def wrap_label(text: str, width: int = 14, max_lines: int = 3) -> str:
    """Wrap compact plot labels so dense figures do not overlap."""
    if not text:
        return ""
    wrapped = textwrap.wrap(str(text), width=width, break_long_words=False)
    if len(wrapped) <= max_lines:
        return "\n".join(wrapped)
    return "\n".join(wrapped[:max_lines - 1] + [wrapped[max_lines - 1] + "..."])


def set_axis_grid(ax, axis: str = "both"):
    """Apply a subtle background grid behind plotted data."""
    ax.set_axisbelow(True)
    ax.grid(True, which="major", axis=axis, color=GRID, linewidth=0.5, alpha=0.85)


def style_legend(legend):
    """Polish legend frame styling."""
    if legend is None:
        return
    frame = legend.get_frame()
    frame.set_facecolor("white")
    frame.set_edgecolor("#D7DEE7")
    frame.set_linewidth(0.8)
