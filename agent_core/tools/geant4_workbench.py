"""Helpers for RadAgent Geant4 self-check and visual workbench workflows."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

SELF_CHECK_EVENTS = 1000
VISUAL_WORKBENCH_EVENTS = 100


def resolve_self_check_events(
    *,
    g4_model_ir: dict[str, Any] | None = None,
    task_spec: dict[str, Any] | None = None,
    default: int = SELF_CHECK_EVENTS,
) -> int:
    """Resolve the runtime self-check event count from the simulation contract."""
    source_events: list[int] = []
    sources = _mapping_get(g4_model_ir, "sources")
    if isinstance(sources, list):
        for source in sources:
            for key in ("events", "num_events", "requested_events"):
                value = _positive_int(_mapping_get(source, key))
                if value is not None:
                    source_events.append(value)
                    break
    if source_events:
        return sum(source_events)

    for key in ("events", "n_events", "num_events"):
        value = _positive_int(_mapping_get(task_spec, key))
        if value is not None:
            return value

    run_plan = _mapping_get(task_spec, "run_plan")
    for key in ("validation_events", "production_events", "events"):
        value = _positive_int(_mapping_get(run_plan, key))
        if value is not None:
            return value

    return max(1, int(default))


def _mapping_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None) if value is not None else None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def prepare_self_check_macro(
    project_dir: str | Path,
    *,
    events: int = SELF_CHECK_EVENTS,
    source_macro: str | Path | None = None,
) -> Path:
    """Create a controlled batch macro with an explicit ``/run/beamOn`` count."""
    if events <= 0:
        raise ValueError("events must be positive")
    root = Path(project_dir)
    macros_dir = root / "macros"
    macros_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source_macro) if source_macro is not None else macros_dir / "run.mac"
    text = source.read_text(encoding="utf-8", errors="replace") if source.is_file() else ""
    text = _strip_visual_commands(text)
    text = _replace_or_append_beam_on(text, events)
    target = macros_dir / f"radagent_self_check_{events}.mac"
    target.write_text(text, encoding="utf-8")
    return target


def prepare_visual_workbench(
    project_dir: str | Path,
    *,
    executable: str | Path,
    events: int = VISUAL_WORKBENCH_EVENTS,
) -> dict[str, Any]:
    """Write B1/B2-style visual macros and return native launch metadata."""
    if events <= 0:
        raise ValueError("events must be positive")
    root = Path(project_dir)
    macros_dir = root / "macros"
    macros_dir.mkdir(parents=True, exist_ok=True)

    init_macro = macros_dir / "init_vis.mac"
    init_alias_macro = macros_dir / "init.mac"
    vis_macro = macros_dir / "vis.mac"
    gui_macro = macros_dir / "gui.mac"
    init_text = _init_vis_macro()
    init_macro.write_text(init_text, encoding="utf-8")
    init_alias_macro.write_text(init_text, encoding="utf-8")
    vis_macro.write_text(_vis_macro(events), encoding="utf-8")
    gui_macro.write_text(_gui_macro(events), encoding="utf-8")

    exe = Path(executable)
    return {
        "project_dir": str(root),
        "events": events,
        "executable": str(exe),
        "working_dir": str(root),
        "init_macro": str(init_macro),
        "vis_macro": str(vis_macro),
        "gui_macro": str(gui_macro),
        "launch_command": [str(exe)],
        "environment": visual_workbench_environment(),
    }


def visual_workbench_environment(
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return the environment additions needed for native Qt/OpenGL workbench launch."""
    source = dict(os.environ if base_env is None else base_env)
    env: dict[str, str] = {}
    if "DISPLAY" in source:
        env["DISPLAY"] = source["DISPLAY"]
    env["QT_QPA_PLATFORM"] = source.get("QT_QPA_PLATFORM") or "xcb"
    return env


def _strip_visual_commands(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("/vis/") or stripped.startswith("/gui/"):
            continue
        if stripped.startswith("/tracking/storeTrajectory"):
            continue
        kept.append(line)
    return "\n".join(kept).strip() + "\n"


def _replace_or_append_beam_on(text: str, events: int) -> str:
    replacement = f"/run/beamOn {events}"
    updated, count = re.subn(
        r"^\s*/run/beamOn\s+\d+\s*$",
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count:
        return updated if updated.endswith("\n") else updated + "\n"
    return text.rstrip() + f"\n{replacement}\n"


def _init_vis_macro() -> str:
    return "\n".join(
        [
            "# RadAgent Geant4 visual workbench initialization",
            "/control/verbose 2",
            "/control/saveHistory",
            "/run/verbose 2",
            "/run/initialize",
            "/control/execute macros/vis.mac",
            "",
        ]
    )


def _vis_macro(events: int) -> str:
    return "\n".join(
        [
            "# RadAgent Geant4 visual workbench",
            "/vis/open",
            "/vis/viewer/set/autoRefresh false",
            "/vis/verbose errors",
            "/vis/drawVolume",
            "/vis/viewer/set/background 1 1 1",
            "/vis/viewer/set/picking true",
            "/vis/viewer/set/style surface",
            "/vis/viewer/set/auxiliaryEdge true",
            "/vis/viewer/set/lineSegmentsPerCircle 100",
            "/vis/viewer/set/viewpointThetaPhi 120 150",
            "/vis/scene/add/scale",
            "/vis/scene/add/axes",
            "/tracking/storeTrajectory 1",
            "/vis/scene/add/trajectories smooth",
            "/vis/modeling/trajectories/create/drawByCharge",
            "/vis/modeling/trajectories/drawByCharge-0/default/setDrawStepPts true",
            "/vis/modeling/trajectories/drawByCharge-0/default/setStepPtsSize 2",
            "/vis/scene/add/hits",
            "/vis/scene/endOfEventAction accumulate",
            f"/run/beamOn {events}",
            "/vis/viewer/set/autoRefresh true",
            "/vis/verbose warnings",
            "/vis/viewer/flush",
            "",
        ]
    )


def _gui_macro(events: int) -> str:
    return "\n".join(
        [
            "# RadAgent Geant4 visual workbench GUI controls",
            "/gui/addMenu file File",
            "/gui/addButton file Quit exit",
            "/gui/addMenu run Run",
            '/gui/addButton run "beamOn 1" "/run/beamOn 1"',
            f'/gui/addButton run "beamOn {events}" "/run/beamOn {events}"',
            "/gui/addMenu viewer Viewer",
            '/gui/addButton viewer "Set style surface" "/vis/viewer/set/style surface"',
            '/gui/addButton viewer "Set style wireframe" "/vis/viewer/set/style wireframe"',
            '/gui/addButton viewer "Refresh viewer" "/vis/viewer/refresh"',
            '/gui/addButton viewer "Flush viewer" "/vis/viewer/flush"',
            "",
        ]
    )
