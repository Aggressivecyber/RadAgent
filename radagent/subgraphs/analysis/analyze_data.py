"""分析子图节点: 读取 CSV 数据，计算统计数据"""

import csv
import logging
from pathlib import Path
from typing import Literal

from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.schemas import AnomalyCheck
from radagent.subgraphs.analysis.state import AnalysisState

_NODE = "analyze_data"

logger = logging.getLogger("radagent.node.tools")


def analyze_data(state: AnalysisState) -> Command[Literal["draw_geometry"]]:
    """读取 CSV 数据，计算深度剂量分布、逐层统计、逐层能谱"""
    log_node_entry(_NODE, state)

    build = state.get("build")
    plan = state.get("sim_plan")
    results = state.get("results", [])

    if not build or not plan:
        log_error(_NODE, "缺少 build 或 sim_plan")
        update = {"parse_error": "分析阶段缺少必要数据"}
        log_node_exit(_NODE, "draw_geometry", update)
        return Command(update=update, goto="draw_geometry")

    work_dir = Path(build.executable_path).parent if build.executable_path else Path(build.source_dir) / "build"
    geometry = plan.geometry
    layers = geometry.layers
    layer_names = [l.name for l in layers]

    # 计算层边界（从表面开始的深度，单位 mm）
    layer_boundaries = [0.0]
    for layer in layers:
        layer_boundaries.append(layer_boundaries[-1] + layer.thickness_mm)
    total_thickness = layer_boundaries[-1]

    # 读取 steps CSV
    steps_file = work_dir / "radagent_steps.csv"
    events_file = work_dir / "radagent_events.csv"

    all_steps = _read_steps_csv(steps_file)
    all_events = _read_events_csv(events_file)

    log_info(_NODE, f"读取 {len(all_steps)} 步进, {len(all_events)} 事件")

    # safe name 映射
    safe_name_map = {}
    for name in layer_names:
        safe = name.replace(" ", "_").replace("（", "_").replace("）", "")
        safe_name_map[safe] = name

    # 逐层能量沉积列表（用于能谱分析）
    per_layer_edeps: dict[str, list[float]] = {name: [] for name in layer_names}
    for step in all_steps:
        vol = step["volume"]
        if vol in safe_name_map:
            edep = step["edep_MeV"]
            if edep > 0:
                per_layer_edeps[safe_name_map[vol]].append(edep)

    per_layer_stats: dict[str, dict] = {}
    for name in layer_names:
        edeps = per_layer_edeps[name]
        total = sum(edeps)
        count = len(edeps)
        mean = total / count if count > 0 else 0.0
        per_layer_stats[name] = {
            "total_edep_MeV": total,
            "num_steps": count,
            "mean_edep_MeV": mean,
            "max_edep_MeV": max(edeps) if edeps else 0.0,
        }
        log_info(_NODE, f"  {name}: total={total:.4e} MeV, steps={count}")

    # 深度剂量分布
    # Geant4 z 坐标 (cm) → depth from surface (mm):
    # surface at z = totalThickness_mm / 2, depth = totalThickness_mm/2 - z_cm*10
    num_depth_bins = 200
    depth_bin_width = total_thickness / num_depth_bins
    depth_dose = [0.0] * num_depth_bins

    # 2D 热力图数据: depth vs x
    num_x_bins = 100
    half_xy_cm = geometry.size_xy_cm * 0.5
    x_bin_width = geometry.size_xy_cm / num_x_bins
    heatmap_2d = [[0.0] * num_x_bins for _ in range(num_depth_bins)]

    for step in all_steps:
        edep = step["edep_MeV"]
        if edep <= 0:
            continue
        z_cm = step["z_cm"]
        x_cm = step["x_cm"]
        depth_mm = total_thickness / 2.0 - z_cm * 10.0

        depth_idx = int(depth_mm / depth_bin_width)
        if 0 <= depth_idx < num_depth_bins:
            depth_dose[depth_idx] += edep
            x_idx = int((x_cm + half_xy_cm) / x_bin_width)
            if 0 <= x_idx < num_x_bins:
                heatmap_2d[depth_idx][x_idx] += edep

    # 异常检测
    anomaly = _check_anomalies(results, plan)
    log_info(_NODE, f"异常检测: status={anomaly.status}")

    # 创建 figures 目录
    figures_dir = work_dir / "figures"
    figures_dir.mkdir(exist_ok=True)

    analysis_data = {
        "work_dir": str(work_dir),
        "figures_dir": str(figures_dir),
        "layer_names": layer_names,
        "layer_boundaries": layer_boundaries,
        "total_thickness_mm": total_thickness,
        "size_xy_cm": geometry.size_xy_cm,
        "depth_dose": depth_dose,
        "depth_bin_width": depth_bin_width,
        "num_depth_bins": num_depth_bins,
        "heatmap_2d": heatmap_2d,
        "num_x_bins": num_x_bins,
        "x_min": -half_xy_cm,
        "x_max": half_xy_cm,
        "x_bin_width": x_bin_width,
        "per_layer_edeps": per_layer_edeps,
        "per_layer_stats": per_layer_stats,
        "num_steps": len(all_steps),
        "num_events": len(all_events),
    }

    update = {
        "analysis_data": analysis_data,
        "anomaly": [anomaly],
        "figure_paths": {},
        "parse_error": "",
    }
    log_node_exit(_NODE, "draw_geometry", {"num_steps": len(all_steps)})
    return Command(update=update, goto="draw_geometry")


def _read_steps_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    steps = []
    try:
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                steps.append({
                    "event_id": int(row.get("event_id", 0)),
                    "step_id": int(row.get("step_id", 0)),
                    "particle": row.get("particle", ""),
                    "kinetic_MeV": float(row.get("kinetic_MeV", 0)),
                    "x_cm": float(row.get("x_cm", 0)),
                    "y_cm": float(row.get("y_cm", 0)),
                    "z_cm": float(row.get("z_cm", 0)),
                    "volume": row.get("volume", ""),
                    "edep_MeV": float(row.get("edep_MeV", 0)),
                    "step_length_mm": float(row.get("step_length_mm", 0)),
                    "process": row.get("process", ""),
                })
    except Exception as e:
        log_error(_NODE, f"读取 steps CSV 失败: {e}")
    return steps


def _read_events_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    try:
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                events.append({
                    "event_id": int(row.get("event_id", 0)),
                    "initial_particle": row.get("initial_particle", ""),
                    "initial_energy_MeV": float(row.get("initial_energy_MeV", 0)),
                    "total_edep_MeV": float(row.get("total_edep_MeV", 0)),
                    "num_steps": int(row.get("num_steps", 0)),
                    "final_kinetic_MeV": float(row.get("final_kinetic_MeV", 0)),
                    "num_secondaries": int(row.get("num_secondaries", 0)),
                })
    except Exception as e:
        log_error(_NODE, f"读取 events CSV 失败: {e}")
    return events


def _check_anomalies(results: list, plan) -> AnomalyCheck:
    """异常检测"""
    details = []
    valid = [r for r in results if r.num_events > 0]
    if not valid:
        return AnomalyCheck(status="high_risk", details="所有场景均无有效输出")

    zero_dose = [r.scenario_name for r in valid if r.total_dose_Gy <= 0]
    if zero_dose:
        details.append(f"零剂量场景: {', '.join(zero_dose)}")

    for r in valid:
        if r.dose_per_event_Gy > 1e6:
            details.append(f"单事件剂量异常高 ({r.scenario_name})")

    if plan and plan.geometry.sensitive_volume:
        hit = any(
            plan.geometry.sensitive_volume in r.layer_doses
            and r.layer_doses[plan.geometry.sensitive_volume] > 0
            for r in valid
        )
        if not hit:
            details.append(f"敏感体积 '{plan.geometry.sensitive_volume}' 未被命中")

    if details:
        return AnomalyCheck(status="suspicious", details="; ".join(details))
    return AnomalyCheck(status="normal", details="")
