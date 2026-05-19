"""节点: 编译和运行 Geant4 仿真（含 Command 重试逻辑）"""

from typing import Literal

from langgraph.types import Command

from radagent.state import RadAgentState
from radagent.schemas import BuildResult, ControlState
from radagent.tools.geant4_tools import build_geant4, run_geant4


def build_and_run(state: RadAgentState) -> Command[Literal["build_and_run", "analyze", "generate_report"]]:
    """编译运行 Geant4，失败时重试"""
    build = state.get("build", BuildResult())
    control = state.get("control", ControlState())
    params = state["sim_params"]

    # 如果还没编译过
    if not build.compile_ok and not build.compile_error:
        print(f"  🔨 编译 Geant4...")
        build = build_geant4(build.source_dir)

        if not build.compile_ok:
            print(f"  ❌ 编译失败: {build.compile_error[:200]}")
            if control.retry_count < control.max_retries:
                return Command(
                    update={"build": build, "control": ControlState(retry_count=control.retry_count + 1, max_retries=control.max_retries)},
                    goto="parameterize",
                )
            return Command(update={"build": build}, goto="generate_report")

        print(f"  ✅ 编译成功: {build.executable_path}")

    # 如果编译成功但还没运行
    if build.compile_ok and not build.run_ok:
        print(f"  🚀 运行仿真 ({params.num_events} events)...")
        run_result = run_geant4(build.executable_path, params.num_events)

        # 合并 build 和 run 结果
        build = BuildResult(
            source_dir=build.source_dir,
            executable_path=build.executable_path,
            compile_ok=True,
            run_ok=run_result.run_ok,
            run_stdout=run_result.run_stdout,
            run_stderr=run_result.run_stderr,
        )

        if not run_result.run_ok:
            print(f"  ❌ 运行失败: {run_result.run_stderr[:200]}")
            if control.retry_count < control.max_retries:
                return Command(
                    update={"build": build, "control": ControlState(retry_count=control.retry_count + 1, max_retries=control.max_retries)},
                    goto="build_and_run",
                )
            return Command(update={"build": build}, goto="generate_report")

        print(f"  ✅ 仿真完成")

    return Command(update={"build": build}, goto="analyze")
