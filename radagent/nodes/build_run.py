"""节点: 编译运行多层 Geant4 仿真（支持多场景并发执行）"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error
from radagent.state import RadAgentState
from radagent.schemas import BuildResult, ControlState, SimulationResult, SimulationScenario
from radagent.tools.geant4_tools import (
    render_multilayer_template,
    build_geant4,
    run_geant4,
    parse_multilayer_output,
)

_NODE = "build_and_run"


def build_and_run(state: RadAgentState) -> Command[Literal["build_and_run", "analyze", "generate_report"]]:
    """编译 Geant4 工程，并发运行所有仿真场景"""
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

    scenarios = plan.scenarios
    geometry = plan.geometry
    layer_names = [l.name for l in geometry.layers]

    # 每个场景独立渲染 + 编译 + 运行（支持不同粒子/能量）
    # 并发执行所有场景
    all_results = []
    compile_failed = False

    log_info(_NODE, f"开始并发执行 {len(scenarios)} 个仿真场景")

    # 单场景时直接执行，多场景时并发
    if len(scenarios) == 1:
        results = _run_scenario(scenarios[0], geometry, layer_names)
        all_results = results
        if not results:
            compile_failed = True
    else:
        n_workers = min(len(scenarios), 4)
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_run_scenario, s, geometry, layer_names): s
                for s in scenarios
            }
            for future in as_completed(futures):
                scenario = futures[future]
                try:
                    results = future.result()
                    if results:
                        all_results.extend(results)
                        log_info(_NODE, f"场景完成: {scenario.name}, "
                                  f"剂量={results[0].total_dose_Gy:.4e} Gy")
                    else:
                        log_error(_NODE, f"场景失败: {scenario.name}")
                        compile_failed = True
                except Exception as e:
                    log_error(_NODE, f"场景异常: {scenario.name}: {e}")

    if compile_failed and not all_results and control.retry_count < control.max_retries:
        update = {
            "control": ControlState(
                retry_count=control.retry_count + 1,
                max_retries=control.max_retries,
            ),
        }
        log_node_exit(_NODE, "parameterize (重试)", update)
        return Command(update=update, goto="parameterize")

    build = BuildResult(
        source_dir=build.source_dir or "",
        compile_ok=bool(all_results),
        run_ok=bool(all_results),
    )

    update = {
        "build": build,
        "results": all_results,
        "parse_error": "",
    }
    log_node_exit(_NODE, "sim_gate", update)
    return Command(update=update, goto="sim_gate")


def _run_scenario(
    scenario: SimulationScenario,
    geometry,
    layer_names: list[str],
) -> list[SimulationResult]:
    """渲染 + 编译 + 运行单个场景，返回结果列表"""
    try:
        source_dir, _ = render_multilayer_template(geometry, scenario)
        log_info(_NODE, f"  [{scenario.name}] 渲染完成: {source_dir}")
    except Exception as e:
        log_error(_NODE, f"  [{scenario.name}] 渲染失败: {e}")
        return []

    build = build_geant4(source_dir)
    if not build.compile_ok:
        log_error(_NODE, f"  [{scenario.name}] 编译失败: {build.compile_error[:300]}")
        return []

    run_result = run_geant4(build.executable_path, scenario.num_events)
    if not run_result.run_ok:
        log_error(_NODE, f"  [{scenario.name}] 运行失败: {run_result.run_stderr[:300]}")
        return []

    work_dir = str(Path(build.executable_path).parent)
    sim_result = parse_multilayer_output(run_result.run_stdout, layer_names, work_dir=work_dir)
    result = SimulationResult(
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

    if result.num_events > 0:
        log_info(_NODE, f"  [{scenario.name}] 剂量={result.total_dose_Gy:.4e} Gy, "
                  f"峰值层={result.peak_layer or 'N/A'}")
        for layer, dose in result.layer_doses.items():
            log_info(_NODE, f"    {layer}: {dose:.4e} J")

    return [result]
