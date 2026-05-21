"""节点: 编译运行多层 Geant4 仿真（支持多场景顺序执行）"""

from pathlib import Path
from typing import Literal

from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.state import RadAgentState
from radagent.schemas import BuildResult, ControlState, SimulationResult
from radagent.tools.geant4_tools import (
    build_geant4,
    run_geant4,
    parse_multilayer_output,
)

_NODE = "build_and_run"


def build_and_run(state: RadAgentState) -> Command[Literal["build_and_run", "analyze", "generate_report"]]:
    """编译 Geant4 工程，然后运行所有仿真场景"""
    log_node_entry(_NODE, state)

    build = state.get("build", BuildResult())
    control = state.get("control", ControlState())
    plan = state.get("sim_plan")

    if not plan:
        log_error(_NODE, "缺少仿真计划")
        return Command(
            update={"parse_error": "缺少仿真计划"},
            goto="generate_report",
        )

    # 阶段 1: 编译
    if not build.compile_ok and not build.compile_error:
        log_info(_NODE, f"开始编译 Geant4... (source_dir={build.source_dir})")
        build = build_geant4(build.source_dir)

        if not build.compile_ok:
            log_error(_NODE, f"编译失败: {build.compile_error[:500]}")
            if control.retry_count < control.max_retries:
                update = {
                    "build": build,
                    "control": ControlState(
                        retry_count=control.retry_count + 1,
                        max_retries=control.max_retries,
                    ),
                }
                log_node_exit(_NODE, "parameterize (重试)", update)
                return Command(update=update, goto="parameterize")
            log_node_exit(_NODE, "generate_report (编译失败)", {"build": build})
            return Command(update={"build": build}, goto="generate_report")

        log_info(_NODE, f"编译成功: {build.executable_path}")

    # 阶段 2: 运行所有场景
    if build.compile_ok and not build.run_ok:
        scenarios = plan.scenarios
        geometry = plan.geometry
        layer_names = [l.name for l in geometry.layers]
        all_results = []

        log_info(_NODE, f"开始运行 {len(scenarios)} 个仿真场景")

        for i, scenario in enumerate(scenarios):
            log_info(_NODE, f"运行场景 {i + 1}/{len(scenarios)}: {scenario.name} ({scenario.num_events} events)")
            run_result = run_geant4(build.executable_path, scenario.num_events)

            if not run_result.run_ok:
                log_error(_NODE, f"场景运行失败: {run_result.run_stderr[:300]}")
                if control.retry_count < control.max_retries:
                    update = {
                        "build": build,
                        "control": ControlState(
                            retry_count=control.retry_count + 1,
                            max_retries=control.max_retries,
                        ),
                    }
                    log_node_exit(_NODE, "build_and_run (重试)", update)
                    return Command(update=update, goto="build_and_run")
                continue

            # 解析输出 — work_dir 为可执行文件所在目录（CSV 文件在这里）
            work_dir = str(Path(build.executable_path).parent)
            sim_result = parse_multilayer_output(run_result.run_stdout, layer_names, work_dir=work_dir)
            sim_result = SimulationResult(
                scenario_name=scenario.name,
                total_dose_Gy=sim_result.total_dose_Gy,
                dose_per_event_Gy=sim_result.dose_per_event_Gy,
                peak_layer=sim_result.peak_layer,
                peak_depth_mm=sim_result.peak_depth_mm,
                penetrated=sim_result.penetrated,
                layer_doses=sim_result.layer_doses,
                num_events=sim_result.num_events,
                raw_summary=sim_result.raw_summary,
            )
            all_results.append(sim_result)

            if sim_result.num_events > 0:
                log_info(_NODE, f"场景结果: 剂量={sim_result.total_dose_Gy:.4e} Gy, "
                          f"峰值层={sim_result.peak_layer or 'N/A'}")
                for layer, dose in sim_result.layer_doses.items():
                    log_info(_NODE, f"  {layer}: {dose:.4e} J")

        # 标记运行完成
        build = BuildResult(
            source_dir=build.source_dir,
            executable_path=build.executable_path,
            compile_ok=True,
            run_ok=True,
            run_stdout="",
            run_stderr="",
        )

        update = {
            "build": build,
            "results": all_results,
            "parse_error": "",
        }
        log_node_exit(_NODE, "analyze", update)
        return Command(update=update, goto="analyze")

    log_node_exit(_NODE, "analyze", {"build": build})
    return Command(update={"build": build}, goto="analyze")
