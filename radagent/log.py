"""RadAgent 日志系统

按会话分目录，每节点独立日志 + 全局时序日志 + JSON state 快照。

目录结构:
  logs/session_YYYYMMDD_HHMMSS/
  ├── pipeline.log            # 全局时序（所有节点混合）
  ├── 01_parse_intent.log     # 按节点独立日志
  ├── ...
  └── state_snapshots/        # JSON state 快照
      ├── 01_parse_intent_entry.json
      └── 01_parse_intent_exit.json
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# 节点编号映射 — 日志文件名前缀
_NODE_ORDER: dict[str, int] = {
    "parse_intent": 1,
    "design_schema": 2,
    "research_params": 3,
    "confirm_params": 4,
    "parameterize": 5,
    "build_and_run": 6,
    "analyze": 7,
    "generate_report": 8,
    "human_review": 9,
}

# 全局会话状态
_session_dir: Path | None = None
_pipeline_logger: logging.Logger | None = None
_initialized: bool = False


def init_session_log(log_root: Path | None = None) -> Path:
    """初始化会话日志目录。返回会话目录路径。"""
    global _session_dir, _pipeline_logger, _initialized

    if _initialized:
        return _session_dir  # type: ignore[return-value]

    if log_root is None:
        log_root = Path(__file__).parent.parent / "logs"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _session_dir = log_root / f"session_{timestamp}"
    _session_dir.mkdir(parents=True, exist_ok=True)
    (_session_dir / "state_snapshots").mkdir(exist_ok=True)

    # pipeline.log — 全局时序日志
    _pipeline_logger = logging.getLogger("radagent.pipeline")
    _pipeline_logger.setLevel(logging.DEBUG)

    handler = logging.FileHandler(_session_dir / "pipeline.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _pipeline_logger.addHandler(handler)
    _pipeline_logger.propagate = False

    _initialized = True
    _pipeline_logger.info("=== 会话开始 ===  目录: %s", _session_dir)

    return _session_dir


def get_session_dir() -> Path:
    """返回当前会话目录。如果未初始化则自动初始化。"""
    if _session_dir is None:
        init_session_log()
    return _session_dir  # type: ignore[return-value]


def get_logger(node_name: str) -> logging.Logger:
    """获取节点专属 logger，同时写入节点独立文件和 pipeline.log。"""
    session = get_session_dir()

    order = _NODE_ORDER.get(node_name, 0)
    prefix = f"{order:02d}_{node_name}" if order else node_name

    logger = logging.getLogger(f"radagent.node.{node_name}")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.FileHandler(session / f"{prefix}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.propagate = False

    return logger


def _pipeline() -> logging.Logger:
    if _pipeline_logger is None:
        init_session_log()
    return _pipeline_logger  # type: ignore[return-value]


def _node_prefix(node_name: str) -> str:
    order = _NODE_ORDER.get(node_name, 0)
    return f"{order:02d}_{node_name}" if order else node_name


def log_node_entry(node_name: str, state: dict[str, Any]) -> None:
    """记录节点进入事件 + state 快照。"""
    logger = get_logger(node_name)
    pipe = _pipeline()

    user_input = state.get("user_input", "")
    parse_error = state.get("parse_error", "")

    msg = f"[{node_name}] === 节点进入 ==="
    if user_input:
        msg += f"  user_input={user_input[:200]}"
    if parse_error:
        msg += f"  parse_error={parse_error[:200]}"

    logger.info(msg)
    pipe.info(msg)

    # JSON state 快照
    _save_state_snapshot(node_name, "entry", state)


def log_node_exit(node_name: str, goto: str, update: dict[str, Any] | None = None) -> None:
    """记录节点退出事件。"""
    logger = get_logger(node_name)
    pipe = _pipeline()

    msg = f"[{node_name}] === 节点退出 → {goto} ==="
    if update:
        summary = _summarize_update(update)
        if summary:
            msg += f"  {summary}"

    logger.info(msg)
    pipe.info(msg)

    # 保存退出时的 state 快照
    if update:
        _save_state_snapshot(node_name, "exit", update)


def log_llm_call(node_name: str, prompt: str, response: str) -> None:
    """记录 LLM 交互（prompt + response 摘要）。"""
    logger = get_logger(node_name)
    pipe = _pipeline()

    logger.debug("LLM prompt (%d chars):\n%s", len(prompt), prompt[:2000])
    logger.debug("LLM response (%d chars):\n%s", len(response), response[:2000])
    pipe.info("[%s] LLM 调用完成 (%d → %d chars)", node_name, len(prompt), len(response))


def log_error(node_name: str, error: str | Exception) -> None:
    """记录错误。"""
    logger = get_logger(node_name)
    pipe = _pipeline()

    error_str = str(error)[:500]
    logger.error("ERROR: %s", error_str)
    pipe.error("[%s] ERROR: %s", node_name, error_str)


def log_info(node_name: str, message: str) -> None:
    """记录一般信息（同时写入节点日志和 pipeline.log）。"""
    logger = get_logger(node_name)
    pipe = _pipeline()
    logger.info(message)
    pipe.info("[%s] %s", node_name, message)


def log_debug(node_name: str, message: str) -> None:
    """记录调试信息（仅写入节点日志）。"""
    logger = get_logger(node_name)
    logger.debug(message)


def _save_state_snapshot(node_name: str, phase: str, state: dict[str, Any]) -> None:
    """将 state 关键字段保存为 JSON 快照。"""
    session = get_session_dir()
    prefix = _node_prefix(node_name)
    snapshot_path = session / "state_snapshots" / f"{prefix}_{phase}.json"

    snapshot = _extract_snapshot(state)
    try:
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass  # 快照写入失败不应影响主流程


def _extract_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """从 state 中提取可序列化的关键字段。"""
    snapshot: dict[str, Any] = {}

    for key in ("user_input", "parse_error"):
        val = state.get(key)
        if val:
            snapshot[key] = val

    # intent_data
    intent = state.get("intent_data")
    if intent:
        snapshot["intent_data"] = intent

    # geometry
    geometry = state.get("geometry")
    if geometry:
        snapshot["geometry"] = {
            "name": getattr(geometry, "name", ""),
            "layers": [
                {
                    "name": l.name,
                    "material": l.material,
                    "geant4_material": getattr(l, "geant4_material", ""),
                    "thickness_mm": l.thickness_mm,
                    "role": getattr(l, "role", ""),
                }
                for l in getattr(geometry, "layers", [])
            ],
            "sensitive_volume": getattr(geometry, "sensitive_volume", ""),
        }

    # orbit
    orbit = state.get("orbit")
    if orbit:
        snapshot["orbit"] = {
            "name": getattr(orbit, "orbit_name", ""),
            "altitude_km": getattr(orbit, "altitude_km", 0),
            "inclination_deg": getattr(orbit, "inclination_deg", 0),
        }

    # sim_plan
    sim_plan = state.get("sim_plan")
    if sim_plan:
        plan_geo = getattr(sim_plan, "geometry", None)
        plan_orbit = getattr(sim_plan, "orbit", None)
        plan_scenarios = getattr(sim_plan, "scenarios", ())
        snapshot["sim_plan"] = {
            "geometry_name": getattr(plan_geo, "name", "") if plan_geo else "",
            "orbit_name": getattr(plan_orbit, "orbit_name", "") if plan_orbit else "",
            "num_scenarios": len(plan_scenarios),
            "scenarios": [
                {
                    "name": s.name,
                    "particle": s.source.particle if hasattr(s, "source") else "",
                    "energy_MeV": s.source.energy_MeV if hasattr(s, "source") else 0,
                    "num_events": s.num_events,
                }
                for s in plan_scenarios
            ] if plan_scenarios else [],
        }

    # build
    build = state.get("build")
    if build:
        snapshot["build"] = {
            "source_dir": getattr(build, "source_dir", ""),
            "executable_path": getattr(build, "executable_path", ""),
            "compile_ok": getattr(build, "compile_ok", False),
            "run_ok": getattr(build, "run_ok", False),
            "compile_error": getattr(build, "compile_error", "")[:500],
        }

    # results
    results = state.get("results", [])
    if results:
        snapshot["results"] = [
            {
                "scenario_name": r.scenario_name,
                "total_dose_Gy": r.total_dose_Gy,
                "num_events": r.num_events,
                "peak_layer": r.peak_layer,
                "penetrated": r.penetrated,
            }
            for r in results
        ]

    # anomaly
    anomaly = state.get("anomaly", [])
    if anomaly:
        snapshot["anomaly"] = [
            {"status": a.status, "details": a.details}
            for a in anomaly
        ]

    # control
    control = state.get("control")
    if control:
        snapshot["control"] = {
            "retry_count": getattr(control, "retry_count", 0),
            "max_retries": getattr(control, "max_retries", 3),
            "approved": getattr(control, "approved", False),
        }

    # report
    report = state.get("report", "")
    if report:
        snapshot["report_length"] = len(report)
        snapshot["report_preview"] = report[:500]

    # scenarios
    scenarios = state.get("scenarios", [])
    if scenarios:
        snapshot["scenarios"] = [
            {
                "name": s.name,
                "particle": s.source.particle if hasattr(s, "source") else "",
                "energy_MeV": s.source.energy_MeV if hasattr(s, "source") else 0,
                "num_events": s.num_events,
                "physics_list": s.physics_list,
            }
            for s in scenarios
        ]

    # orbit_env_data
    orbit_env = state.get("orbit_env_data")
    if orbit_env:
        snapshot["orbit_env_data"] = orbit_env

    # search_results
    search = state.get("search_results", "")
    if search:
        snapshot["search_results_length"] = len(search)

    return snapshot


# ---------------------------------------------------------------------------
# 状态查看 — 可从任意终端调用
# ---------------------------------------------------------------------------

# 管线节点顺序（用于判定进度百分比）
_PIPELINE_STEPS: list[str] = [
    "parse_intent", "design_schema", "research_params", "confirm_params",
    "parameterize", "build_and_run", "analyze", "generate_report", "human_review",
]


def get_status() -> dict[str, Any]:
    """返回当前管线运行状态。

    从 pipeline.log 解析最新事件，判断：
    - 当前在哪个节点
    - 进度百分比
    - 是否卡住（节点重试次数）
    - 最近错误
    - 运行时长

    可在程序运行时从另一个终端调用::

        python -c "from radagent.log import get_status; import json; print(json.dumps(get_status(), ensure_ascii=False, indent=2))"
    """
    from radagent.config import LOG_DIR

    result: dict[str, Any] = {
        "running": False,
        "session_dir": None,
        "current_node": None,
        "progress_pct": 0,
        "retries": {},
        "last_error": None,
        "elapsed_sec": 0,
    }

    # 找最新会话目录
    if not LOG_DIR.exists():
        return result

    sessions = sorted(LOG_DIR.glob("session_*"))
    if not sessions:
        return result

    latest = sessions[-1]
    result["session_dir"] = str(latest)

    pipeline_log = latest / "pipeline.log"
    if not pipeline_log.exists():
        return result

    lines = pipeline_log.read_text(encoding="utf-8").splitlines()
    if not lines:
        return result

    # 解析日志行
    current_node = None
    last_entry_time: datetime | None = None
    last_exit_time: datetime | None = None
    session_start_time: datetime | None = None
    node_retries: dict[str, int] = {}
    last_error_msg: str | None = None

    for line in lines:
        # 时间戳解析
        time_str = line[:23].strip()
        try:
            ts = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, IndexError):
            continue

        if "=== 会话开始 ===" in line:
            session_start_time = ts
            continue

        if "=== 节点进入 ===" in line:
            # 格式: ... [INFO] [node_name] === 节点进入 ===
            # 节点名在第二个 [] 中
            node = _extract_node_name(line)
            if node:
                current_node = node
                last_entry_time = ts
                result["running"] = True

        elif "=== 节点退出 →" in line:
            node = _extract_node_name(line)
            if node:
                last_exit_time = ts
                if "(重试)" in line:
                    node_retries[node] = node_retries.get(node, 0) + 1

        elif "ERROR:" in line:
            err_idx = line.find("ERROR: ")
            if err_idx >= 0:
                last_error_msg = line[err_idx + 7:][:200]

    # 组装结果
    result["current_node"] = current_node
    result["retries"] = node_retries
    result["last_error"] = last_error_msg

    # 进度百分比
    if current_node and current_node in _PIPELINE_STEPS:
        idx = _PIPELINE_STEPS.index(current_node)
        result["progress_pct"] = round((idx + 1) / len(_PIPELINE_STEPS) * 100)

    # 运行时长
    if session_start_time and last_entry_time:
        result["elapsed_sec"] = int((last_entry_time - session_start_time).total_seconds())

    # 判断是否卡住（某节点重试 >= 3 次）
    stuck_nodes = [n for n, cnt in node_retries.items() if cnt >= 3]
    if stuck_nodes:
        result["stuck"] = True
        result["stuck_nodes"] = stuck_nodes
    else:
        result["stuck"] = False

    return result


def _extract_node_name(line: str) -> str | None:
    """从日志行提取节点名。格式: ... [INFO] [node_name] ..."""
    # 跳过第一个 []（日志级别），提取第二个 []
    parts = line.split("]")
    if len(parts) >= 3:
        # parts[0] = "2026-05-22 03:59:14.158 [INFO"
        # parts[1] = " [parse_intent"
        candidate = parts[1].strip().lstrip("[")
        if candidate in _NODE_ORDER or candidate in ("main",):
            return candidate
        # 也可能是子图内部节点
        if candidate:
            return candidate
    return None


def print_status() -> None:
    """打印格式化的状态摘要到终端。"""
    status = get_status()
    if not status["running"] and status["current_node"] is None:
        print("无运行中的会话")
        return

    node = status["current_node"] or "?"
    pct = status["progress_pct"]
    elapsed = status["elapsed_sec"]
    mins, secs = divmod(elapsed, 60)

    bar_len = 30
    filled = int(bar_len * pct / 100)
    bar = "#" * filled + "-" * (bar_len - filled)

    print(f"状态: {'运行中' if status['running'] else '已停止'}")
    print(f"进度: [{bar}] {pct}%  当前节点: {node}")
    print(f"耗时: {mins}m {secs}s  会话: {status['session_dir']}")

    if status.get("stuck"):
        print(f"警告: 节点卡住 {status['stuck_nodes']} (重试次数过多)")

    if status["retries"]:
        retry_str = ", ".join(f"{n}={c}次" for n, c in status["retries"].items())
        print(f"重试: {retry_str}")

    if status["last_error"]:
        print(f"最后错误: {status['last_error'][:150]}")


def _summarize_update(update: dict[str, Any]) -> str:
    """将 Command.update 摘要为一行字符串。"""
    parts = []
    for key, val in update.items():
        if key == "parse_error" and val:
            parts.append(f"parse_error={str(val)[:100]}")
        elif key == "build":
            parts.append(f"build(compile={getattr(val, 'compile_ok', '?')}, run={getattr(val, 'run_ok', '?')})")
        elif key == "sim_plan":
            parts.append("sim_plan=已设置")
        elif key == "geometry":
            parts.append(f"geometry={getattr(val, 'name', '?')}")
        elif key == "results":
            parts.append(f"results({len(val)} scenarios)")
        elif key == "anomaly":
            parts.append(f"anomaly({len(val)} items)")
        elif key == "scenarios":
            parts.append(f"scenarios({len(val)} items)")
        elif key == "control":
            parts.append(f"control(retry={getattr(val, 'retry_count', '?')})")
        elif key == "report":
            parts.append(f"report({len(val)} chars)")
    return " | ".join(parts)
