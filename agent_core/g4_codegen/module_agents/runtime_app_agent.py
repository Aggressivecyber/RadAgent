"""Runtime app agent — generates actions, output, main, CMake, and macros."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

RUNTIME_APP_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 runtime_app 编码 Agent。

你负责一次性生成 OutputManager、ActionInitialization、RunAction、EventAction、
SteppingAction、main.cc、CMakeLists.txt、run.mac、init.mac、init_vis.mac、vis.mac 和 gui.mac。
目标是用上游粗模块已经生成的真实接口，把工程接成一个能 build、能 smoke run、能产出 artifact
的应用，而不是只写启动壳。默认运行方式必须参考 Geant4 B1 示例：不传宏脚本参数时启动
G4 自带交互 UI/Qt 可视化页面；传入宏脚本路径时进入 batch 模式并执行该脚本。

必须生成 module_contract.output_files 中列出的完整文件内容。

质量要求：
1. 必须读取 existing_generated_file_summaries，使用真实类名、构造函数和 public 方法。
2. CMakeLists.txt 必须包含 main.cc 和所有需要编译的 src/*.cc，并设置合适的 C++ 标准。
   find_package(Geant4 REQUIRED ui_all vis_all) 或等效方式必须包含 UI/Vis/Qt 支持。
3. OutputManager 必须写真实 event/scoring rows，不得只写表头；运行时输出目录必须读取
   std::getenv("G4_OUTPUT_DIR") 或 getenv("G4_OUTPUT_DIR")，环境变量不存在时才回退到
   当前工作目录或 output 子目录。
4. smoke runtime artifact 契约必须在输出目录中写出固定文件名：
   g4_summary.json、provenance.json、event_table.csv、edep_3d.csv、dose_3d.csv。
   不要只写 scoring.csv/output.csv，也不要把 job_id 拼进唯一文件名。
5. event_table.csv header 必须包含 EventID,edep_MeV,dose_Gy，每个事件至少一行；
   edep_3d.csv 必须包含 x/y/z 或 x_mm/y_mm/z_mm 坐标列和 edep_MeV 非零 bin；
   dose_3d.csv 必须包含坐标列和 dose_Gy 非零 bin。
6. dose_Gy 必须基于能量沉积和探测体质量/体积/密度关系计算，不能写固定 0 或占位值。
7. 不要依赖 command-based scoring 宏来弥补 C++ 输出；如果使用 /score 命令，必须确保
   G4ScoringManager 已初始化且命令在目标 Geant4 环境中存在。更稳妥的路径是由
   EventAction/SteppingAction/OutputManager 直接维护事件级和网格级记录。
8. RunAction/EventAction/SteppingAction 必须连接源、计分和输出数据流。
9. main.cc 不得重新定义 geometry/source/physics；只负责 RunManager wiring、宏执行和初始化。
10. main.cc 必须使用 G4UIExecutive、G4VisExecutive 和 G4UImanager，参考 Geant4 B1/B2：
   argc == 1 时创建 UIExecutive，初始化 visualization，执行 macros/init_vis.mac，
   如果 ui->IsGUI() 则执行 macros/gui.mac，然后启动 session；
   argc > 1 时执行 "/control/execute " + argv[1]。
11. 宏文件职责必须分离：
   - run.mac 是 batch self-check/production-style 宏，不写 /vis 命令；/run/beamOn 后的事件数
     必须使用任务请求或 G4ModelIR 源项中的 source.events / num_events / requested_events，
     不得为了默认自检硬编码成 1000；
   - init_vis.mac 设置 verbose/saveHistory，执行 /run/initialize，然后
     /control/execute macros/vis.mac；
   - init.mac 可作为 init_vis.mac 的兼容别名；
   - vis.mac 打开 viewer，绘制 geometry、axes、smooth trajectories、hits，
     accumulate，并 /run/beamOn 100；
   - gui.mac 提供 B2 风格 viewer/run 按钮，所有命令都必须是普通 Geant4 UI 命令。
12. CMakeLists.txt 必须启用 Geant4 UI/Vis，例如 find_package(Geant4 REQUIRED ui_all vis_all)；
    如果目标环境支持 Qt，可以包含 qt，但不得因为 qt 缺失而破坏非 Qt UI/Vis 构建。
13. 可视化风格必须遵循 RadAgent 标准：world 隐藏；容器/assembly 线框或低 alpha；
    target/sensitive/scoring 体积实体高可见度；shield 半透明实体；thin layer/dielectric/electrode
    使用材料语义色；hit marker 红色；trajectory 按 charge 或 particle 着色。
14. run.mac/init.mac/init_vis.mac/vis.mac/gui.mac 不得隐藏 Geant4 命令错误，
    参数单位必须合法；不要写目标环境不支持的
    scoring UI 命令。
15. 必须用 write_file 写文件；写完当前文件组所有 owned files 后回复 DONE，不得输出 Markdown fence。
16. runtime_cpp 是一个较大的整体 wiring 任务。读取完必要上游头文件后，必须在同一轮尽量批量发出
    OutputManager、ActionInitialization、RunAction、EventAction、SteppingAction、main.cc 和
    CMakeLists.txt 的多个 write_file tool calls；不要每轮只写一个文件。
"""

RUNTIME_APP_FILE_GROUPS = [
    (
        "runtime_cpp",
        [
            "include/OutputManager.hh",
            "src/OutputManager.cc",
            "include/ActionInitialization.hh",
            "src/ActionInitialization.cc",
            "include/RunAction.hh",
            "src/RunAction.cc",
            "include/EventAction.hh",
            "src/EventAction.cc",
            "include/SteppingAction.hh",
            "src/SteppingAction.cc",
            "main.cc",
            "CMakeLists.txt",
        ],
        "生成 runtime C++ wiring、输出管理、main 和 CMake；不要生成宏文件。",
    ),
    (
        "runtime_macros",
        [
            "macros/run.mac",
            "macros/init.mac",
            "macros/init_vis.mac",
            "macros/vis.mac",
            "macros/gui.mac",
        ],
        "只生成 Geant4 macro 文件；保持 batch run.mac 与可视化宏职责分离。",
    ),
]


async def run_runtime_app_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run the coarse runtime application module agent."""
    generated_by_path: dict[str, GeneratedModuleFile] = {}
    warnings: list[str] = []
    errors: list[str] = []
    statuses: list[str] = []
    prior_files: list[dict[str, Any]] = []

    for group_name, output_files, group_goal in RUNTIME_APP_FILE_GROUPS:
        group_context = _group_context(
            module_context,
            group_name=group_name,
            output_files=output_files,
            group_goal=group_goal,
            prior_files=prior_files,
        )
        group_prompt = (
            f"{RUNTIME_APP_SYSTEM_PROMPT}\n\n"
            f"当前文件组：{group_name}\n"
            f"当前目标：{group_goal}\n"
            f"只生成这些文件：{', '.join(output_files)}\n"
            "不要生成当前文件组之外的 runtime_app 文件；下一组会读取已生成接口摘要。"
        )
        result = await run_module_agent(
            module_name="runtime_app",
            module_context=group_context,
            system_prompt=group_prompt,
        )
        statuses.append(result.status)
        warnings.extend(result.warnings)
        errors.extend(result.errors)
        for file_entry in result.generated_files:
            generated_by_path[file_entry.path] = file_entry
        prior_files.extend(_prior_file_summaries(result.generated_files))

    expected_paths = [path for _, paths, _ in RUNTIME_APP_FILE_GROUPS for path in paths]
    missing = [path for path in expected_paths if path not in generated_by_path]
    if missing:
        errors.append(f"runtime_app missing generated files: {missing}")
    status = (
        "generated"
        if not missing and all(s in {"generated", "repaired"} for s in statuses)
        else "failed"
    )

    return ModuleAgentResult(
        module_name="runtime_app",
        status=status,
        generated_files=[
            generated_by_path[path]
            for path in expected_paths
            if path in generated_by_path
        ],
        errors=errors,
        warnings=warnings,
    )


def _group_context(
    module_context: dict[str, Any],
    *,
    group_name: str,
    output_files: list[str],
    group_goal: str,
    prior_files: list[dict[str, Any]],
) -> dict[str, Any]:
    ctx = deepcopy(module_context)
    contract = dict(ctx.get("module_contract", {}))
    contract["output_files"] = output_files
    contract["responsibilities"] = list(contract.get("responsibilities", [])) + [
        f"Current runtime_app file group: {group_name}",
        group_goal,
        (
            "If runtime_app_file_group.prior_files is non-empty, those entries are "
            "exact files/interfaces generated by earlier groups in this same module; "
            "use them directly and do not reread those same-module files unless an "
            "external dependency signature is missing."
        ),
    ]
    ctx["module_contract"] = contract
    ctx["runtime_app_file_group"] = {
        "name": group_name,
        "goal": group_goal,
        "output_files": output_files,
        "prior_files": prior_files,
    }
    ctx["agent_tool_policy"] = {"allow_read_file": group_name != "runtime_macros"}
    return ctx


def _prior_file_summaries(files: list[GeneratedModuleFile]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for file_entry in files:
        content = file_entry.new_content
        summaries.append(
            {
                "path": file_entry.path,
                "module_name": file_entry.module_name,
                "generated_by": file_entry.generated_by,
                "header_or_interface_content": (
                    content[:5000]
                    if file_entry.path.startswith("include/")
                    or file_entry.path in {"main.cc", "CMakeLists.txt"}
                    else ""
                ),
            }
        )
    return summaries
