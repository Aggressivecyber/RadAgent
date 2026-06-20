"""Runtime app agent — generates actions, output, main, CMake, and macros."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from agent_core.g4_codegen.cmake_template import RADAGENT_CMAKE_TEMPLATE
from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult
from agent_core.tools.geant4_workbench import VISUAL_WORKBENCH_EVENTS
from agent_core.tools.geant4_workbench import resolve_self_check_events

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
   g4_summary.json 必须包含 events_requested 字段，值等于实际 /run/beamOn 事件数；
   可以同时保留 total_events，但不能只写 total_events 或 num_events_requested。
   OutputManager.hh 与 OutputManager.cc 的 private/public 方法签名必须完全一致；
   不要在 .cc 额外定义头文件未声明的空 overload，例如无参 WriteSummaryJson()。
5. 浏览器 3D 工作台 artifact 契约必须在输出目录中写出固定文件名：
   geometry_view.json、particle_tracks.json、energy_deposits.json。
   - geometry_view.json 必须包含前端可直接渲染的组件列表：id/name/shape/material/size_mm/
     position_mm/rotation_deg/opacity，不得只写空数组；shape 必须保留 G4ModelIR 中的
     geometry_type（例如 cylinder/tube 必须输出 cylinder，不能因为 size_mm 是三元数组就
     硬编码成 box）；
     不要引用不存在的数据成员。只有 OutputManager.hh 明确声明
     std::vector<GeometryComponent> fGeometryComponents 时，OutputManager.cc 才能访问
     fGeometryComponents；否则必须直接从 G4ModelIR 组件写 geometry_view.json，避免
     “fGeometryComponents was not declared in this scope” 编译失败；
   - particle_tracks.json 必须记录真实 step 轨迹点，结构为 tracks 数组，每条包含
     event_id、track_id、particle、energy_MeV、points_mm。points_mm 必须来自 SteppingAction
     或 Geant4 trajectory/step 数据，不得伪造 source-to-target 直线或固定模板；
   - energy_deposits.json 必须记录红色能量沉积点，结构为 deposits 数组，每条包含
     event_id、track_id、volume、position_mm、edep_MeV。只记录 edep_MeV > 0 的真实 step/hit。
   这些文件用于 RadAgent Web 的先 100 粒子 3D 预览；最多保留前 100 个事件/轨迹，避免文件过大。
6. event_table.csv header 必须包含 EventID,edep_MeV,dose_Gy，每个事件至少一行；
   edep_3d.csv 必须包含 x/y/z 或 x_mm/y_mm/z_mm 坐标列和 edep_MeV 非零 bin；
   dose_3d.csv 必须包含坐标列和 dose_Gy 非零 bin。
   如果 event rows 需要从 AddEnergyDepositPoint/energy_deposits 推导，event_table.csv 和 g4_summary.json
   必须使用同一个派生事件行集合；不得只修 summary 或只修 event table，
   也不得让局部变量泄漏到 WriteProvenanceJson 等其它函数。
7. dose_Gy 必须基于能量沉积和探测体质量/体积/密度关系计算，不能写固定 0 或占位值。
8. 不要依赖 command-based scoring 宏来弥补 C++ 输出；如果使用 /score 命令，必须确保
   G4ScoringManager 已初始化且命令在目标 Geant4 环境中存在。更稳妥的路径是由
   EventAction/SteppingAction/OutputManager 直接维护事件级和网格级记录。
9. RunAction/EventAction/SteppingAction 必须连接源、计分、真实 step 轨迹、能量沉积点和输出数据流。
   若 OutputManager 提供 AddTrackPoint/AddEnergyDepositPoint，SteppingAction 构造函数必须接收
   OutputManager*，保存为 fOutputManager，并在 UserSteppingAction 中用真实 eventID/trackID/position/edep
   调用 AddTrackPoint 和 AddEnergyDepositPoint；ActionInitialization 必须把 fOutputManager 传给
   SteppingAction。不得只留下注释说明“稍后再接 OutputManager”。
10. main.cc 不得重新定义 geometry/source/physics；只负责 RunManager wiring、宏执行和初始化。
    创建输出目录必须用 std::filesystem::create_directories(outDir)，不得调用
    std::system("mkdir -p ...") 或其它 shell 命令。
    如果上游 G4ModelIR 与已确认需求给出的 source/material/scoring 不一致，不得在
    main.cc 临时硬编码一个“能跑”的替代物理模型；应使用上游模块真实接口并让
    repair/modeling 修正 IR。
11. main.cc 必须使用 G4UIExecutive、G4VisExecutive 和 G4UImanager，参考 Geant4 B1/B2：
   argc == 1 时创建 UIExecutive，初始化 visualization，执行 macros/init_vis.mac，
   如果 ui->IsGUI() 则执行 macros/gui.mac，然后启动 session；
   argc > 1 时执行 "/control/execute " + argv[1]。
12. 宏文件职责必须分离：
   - run.mac 是 batch self-check/production-style 宏，不写 /vis 命令；/run/beamOn 后的事件数
     必须使用任务请求或 G4ModelIR 源项中的 source.events / num_events / requested_events，
     不得为了默认自检硬编码成 1000；
   - init_vis.mac 设置 verbose/saveHistory，执行 /run/initialize，然后
     /control/execute macros/vis.mac；
   - init.mac 可作为 init_vis.mac 的兼容别名；
   - vis.mac 打开 viewer，绘制 geometry、axes、smooth trajectories、hits，
     accumulate，并 /run/beamOn 100；
   - gui.mac 提供 B2 风格 viewer/run 按钮，所有命令都必须是普通 Geant4 UI 命令。
13. CMakeLists.txt 必须启用 Geant4 UI/Vis，例如 find_package(Geant4 REQUIRED ui_all vis_all)；
    如果目标环境支持 Qt，可以包含 qt，但不得因为 qt 缺失而破坏非 Qt UI/Vis 构建。
14. 可视化风格必须遵循 RadAgent 标准：world 隐藏；容器/assembly 线框或低 alpha；
    target/sensitive/scoring 体积实体高可见度；shield 半透明实体；thin layer/dielectric/electrode
    使用材料语义色；hit marker 红色；trajectory 按 charge 或 particle 着色。
15. run.mac/init.mac/init_vis.mac/vis.mac/gui.mac 不得隐藏 Geant4 命令错误，
    参数单位必须合法；不要写目标环境不支持的
    scoring UI 命令，也不要写 /run/setCutForGamma、/run/setCutForElectron、
    /run/setCutForPositron 这类目标 Geant4 环境可能不存在的命令；需要 cut 时用
    /run/setCut <value> <unit> 或在 PhysicsListFactoryWrapper C++ 中设置。
16. 必须用 write_file 写文件；写完当前文件组所有 owned files 后回复 DONE，不得输出 Markdown fence。
17. runtime_cpp 是一个较大的整体 wiring 任务。读取完必要上游头文件后，必须在同一轮尽量批量发出
    OutputManager、ActionInitialization、RunAction、EventAction、SteppingAction、main.cc 和
    CMakeLists.txt 的多个 write_file tool calls；不要每轮只写一个文件。
18. C++ include/API 对齐必须一次性处理：任何 G4ThreeVector 字段或参数 include "G4ThreeVector.hh"；
    任何 G4Event 使用 include "G4Event.hh"；任何 std::vector/std::map/std::array 使用必须包含
    <vector>/<map>/<array>；调用 SensitiveDetector、ScoringManager、DetectorConstruction 时必须按
    existing_generated_file_summaries 中的真实构造函数和 public 方法签名传参。
19. smoke 崩溃常见根因必须预防：包裹/屏蔽体与被包裹体同级重叠会触发 GeomVol1002/core dumped；
    过细 voxel grid 会触发 std::length_error / max_size。OutputManager/ScoringManager 写
    edep_3d.csv、dose_3d.csv、event_table.csv 前必须限制 bin 数并保证即使无 hit 也写出契约文件。
20. 不得留下 placeholder event_id/track_id 或 "use 0 as placeholder" 注释。SteppingAction 必须从
    G4Step::GetTrack() 取得 track_id，从当前 G4Event 或 EventAction 传入 event_id，并把真实 id 写入
    particle_tracks.json/energy_deposits.json。
21. main.cc 使用 PhysicsListFactoryWrapper 返回的物理列表时，必须 include 正确 Geant4 物理列表头并
    采用可编译的指针类型；不要依赖 forward declaration 猜测 G4VModularPhysicsList/G4VUserPhysicsList 转换。
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
        ],
        "生成 runtime C++ wiring 和输出管理；不要生成 main、CMake 或宏文件。",
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

RUNTIME_APP_CPP_TEMPLATE_FILES = ["main.cc", "CMakeLists.txt"]


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
        if group_name == "runtime_macros":
            macro_files = _build_runtime_macro_files(
                module_context,
                output_files=output_files,
            )
            statuses.append("generated")
            for file_entry in macro_files:
                generated_by_path[file_entry.path] = file_entry
            prior_files.extend(_prior_file_summaries(macro_files))
            continue

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
        _harden_runtime_output_data_flow(generated_by_path)
        _harden_runtime_geometry_view(generated_by_path, module_context)
        prior_files.extend(_prior_file_summaries(result.generated_files))
        if group_name == "runtime_cpp":
            template_files = _build_runtime_cpp_template_files(
                module_context,
                output_files=RUNTIME_APP_CPP_TEMPLATE_FILES,
                generated_by_path=generated_by_path,
            )
            for file_entry in template_files:
                generated_by_path[file_entry.path] = file_entry
            prior_files.extend(_prior_file_summaries(template_files))

    expected_paths = [
        *RUNTIME_APP_FILE_GROUPS[0][1],
        *RUNTIME_APP_CPP_TEMPLATE_FILES,
        *RUNTIME_APP_FILE_GROUPS[1][1],
    ]
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


def _harden_runtime_geometry_view(
    generated_by_path: dict[str, GeneratedModuleFile],
    module_context: dict[str, Any],
) -> None:
    output_source = generated_by_path.get("src/OutputManager.cc")
    output_header = generated_by_path.get("include/OutputManager.hh")
    if not output_source:
        return
    if (
        "WriteGeometryViewJson" not in output_source.new_content
        and "geometry_view.json" not in output_source.new_content
    ):
        return
    components = _ir_geometry_components_for_output(
        module_context.get("g4_model_ir_subset") or {}
    )
    if not components:
        return

    content = (
        output_source.new_content
        if "_RadAgentIrGeometryComponents" in output_source.new_content
        else _insert_ir_geometry_helper(output_source.new_content, components)
    )
    has_geometry_collection = bool(
        re.search(
            r"\b(?:std::)?vector\s*<[^;>]*GeometryComponent[^;>]*>\s*fGeometryComponents\b",
            output_source.new_content + "\n" + (output_header.new_content if output_header else ""),
        )
    )
    has_output_dir = "fOutputDir" in (
        output_source.new_content + "\n" + (output_header.new_content if output_header else "")
    )
    if has_geometry_collection:
        content = _insert_ir_geometry_fallback_in_writer(content)
    elif "WriteGeometryViewJson" in content:
        content = _replace_geometry_writer_with_ir_output(content, has_output_dir=has_output_dir)
    else:
        content = _replace_inline_geometry_writer_with_ir_output(content)
    _replace_generated_content(
        output_source,
        content,
        "deterministically provided IR geometry fallback for geometry_view.json",
    )


def _harden_runtime_output_data_flow(
    generated_by_path: dict[str, GeneratedModuleFile],
) -> None:
    """Patch recurring partial runtime wiring before the expensive runtime gate."""
    output_header = generated_by_path.get("include/OutputManager.hh")
    stepping_header = generated_by_path.get("include/SteppingAction.hh")
    stepping_source = generated_by_path.get("src/SteppingAction.cc")
    action_source = generated_by_path.get("src/ActionInitialization.cc")
    if not output_header or not stepping_header or not stepping_source or not action_source:
        return
    output_content = output_header.new_content
    if "AddTrackPoint" not in output_content or "AddEnergyDepositPoint" not in output_content:
        return
    if (
        "OutputManager*" in stepping_header.new_content
        and "AddTrackPoint" in stepping_source.new_content
        and "AddEnergyDepositPoint" in stepping_source.new_content
        and "fOutputManager" in action_source.new_content
    ):
        return

    _replace_generated_content(
        stepping_header,
        _harden_stepping_header_output_manager(stepping_header.new_content),
        "deterministically wired OutputManager into SteppingAction interface",
    )
    _replace_generated_content(
        stepping_source,
        _harden_stepping_source_output_manager(stepping_source.new_content),
        "deterministically recorded step tracks and deposits through OutputManager",
    )
    _replace_generated_content(
        action_source,
        _harden_action_initialization_stepping_output(action_source.new_content),
        "deterministically passed OutputManager into SteppingAction",
    )


def _replace_generated_content(
    file_entry: GeneratedModuleFile,
    content: str,
    rationale: str,
) -> None:
    if content == file_entry.new_content:
        return
    file_entry.new_content = content
    file_entry.generated_by = f"{file_entry.generated_by}+runtime_contract_postprocess"
    file_entry.rationale = f"{file_entry.rationale}; {rationale}"


def _harden_stepping_header_output_manager(content: str) -> str:
    if "class OutputManager;" not in content:
        content = content.replace("class ScoringManager;\n", "class ScoringManager;\nclass OutputManager;\n", 1)
    content = re.sub(
        r"SteppingAction\s*\(\s*EventAction\*\s*eventAction\s*,\s*ScoringManager\*\s*scoringMgr\s*\)",
        "SteppingAction(EventAction* eventAction, ScoringManager* scoringMgr, OutputManager* outputMgr)",
        content,
        count=1,
    )
    if "fOutputManager" not in content and "ScoringManager* fScoringManager;" in content:
        content = content.replace(
            "ScoringManager* fScoringManager;",
            "ScoringManager* fScoringManager;\n  OutputManager*  fOutputManager;",
            1,
        )
    if "fOutputManager" not in content and "ScoringManager* fScoringManager;" not in content:
        content = re.sub(
            r"(?P<indent>[ \t]*)ScoringManager\*\s+([A-Za-z_]\w*)\s*;",
            r"\g<indent>ScoringManager* \2;\n\g<indent>OutputManager*  fOutputManager;",
            content,
            count=1,
        )
    return content


def _harden_stepping_source_output_manager(content: str) -> str:
    if '#include "OutputManager.hh"' not in content:
        content = content.replace(
            '#include "EventAction.hh"\n',
            '#include "EventAction.hh"\n#include "OutputManager.hh"\n',
            1,
        )
    content = re.sub(
        r"SteppingAction::SteppingAction\s*\(\s*EventAction\*\s*eventAction\s*,\s*ScoringManager\*\s*scoringMgr\s*\)",
        "SteppingAction::SteppingAction(EventAction* eventAction, ScoringManager* scoringMgr,\n                               OutputManager* outputMgr)",
        content,
        count=1,
    )
    content = re.sub(
        r"(:\s*(?:G4UserSteppingAction\(\)\s*,\s*)?fEventAction\s*\(\s*eventAction\s*\)\s*,\s*fScoringManager\s*\(\s*scoringMgr\s*\))",
        r"\1,\n      fOutputManager(outputMgr)",
        content,
        count=1,
    )
    if "fOutputManager(outputMgr)" not in content:
        content = re.sub(
            r"(:\s*fEventAction\s*\(\s*eventAction\s*\)\s*,\s*fScoringManager\s*\(\s*scoringMgr\s*\))",
            r"\1,\n      fOutputManager(outputMgr)",
            content,
            count=1,
        )
    if "AddTrackPoint" in content and "AddEnergyDepositPoint" in content:
        return content

    block = (
        "    if (fOutputManager && eventID >= 0 && eventID < 100) {\n"
        "        TrackPoint tp;\n"
        "        tp.eventID = eventID;\n"
        "        tp.trackID = trackID;\n"
        "        tp.particle = particleName;\n"
        "        tp.energy_MeV = kineticEnergy;\n"
        "        tp.x_mm = pos.x() / mm;\n"
        "        tp.y_mm = pos.y() / mm;\n"
        "        tp.z_mm = pos.z() / mm;\n"
        "        fOutputManager->AddTrackPoint(tp);\n"
        "\n"
        "        if (edep > 0.0) {\n"
        "            EnergyDepositPoint edp;\n"
        "            edp.eventID = eventID;\n"
        "            edp.trackID = trackID;\n"
        "            edp.volume = volumeName;\n"
        "            edp.x_mm = pos.x() / mm;\n"
        "            edp.y_mm = pos.y() / mm;\n"
        "            edp.z_mm = pos.z() / mm;\n"
        "            edp.edep_MeV = edep / MeV;\n"
        "            fOutputManager->AddEnergyDepositPoint(edp);\n"
        "        }\n"
        "    }\n"
    )
    return _insert_before_function_closing_brace(
        content,
        "SteppingAction::UserSteppingAction",
        block,
    )


def _harden_action_initialization_stepping_output(content: str) -> str:
    return re.sub(
        r"new\s+SteppingAction\s*\(\s*eventAction\s*,\s*scoringMgr\s*\)",
        "new SteppingAction(eventAction, scoringMgr, fOutputManager)",
        content,
        count=1,
    )


def _insert_ir_geometry_helper(content: str, components: list[dict[str, Any]]) -> str:
    if "_RadAgentIrGeometryComponents" in content:
        return content
    body = "".join(
        "    "
        + json.dumps(component, ensure_ascii=True, separators=(", ", ": "))
        + ("," if index + 1 < len(components) else "")
        + "\n"
        for index, component in enumerate(components)
    )
    helper = (
        "namespace {\n"
        "const char* _RadAgentIrGeometryComponents()\n"
        "{\n"
        f"    return R\"RADGEOM({body})RADGEOM\";\n"
        "}\n"
        "}\n\n"
    )
    return _insert_after_include_block(content, helper)


def _insert_ir_geometry_fallback_in_writer(content: str) -> str:
    function_name = "OutputManager::WriteGeometryViewJson"
    start = content.find(function_name)
    if start < 0:
        return content
    open_brace = content.find("{", start)
    if open_brace < 0:
        return content
    close_brace = _find_matching_brace(content, open_brace)
    if close_brace < 0:
        return content

    body = content[open_brace + 1 : close_brace]
    stream_match = re.search(
        r"(?P<indent>[ \t]*)std::ofstream\s+(?P<stream>[A-Za-z_]\w*)\s*\([^;]*\);\s*\n",
        body,
    )
    if not stream_match:
        return content
    indent = stream_match.group("indent") or "    "
    stream = stream_match.group("stream")
    fallback = (
        f"{indent}if (fGeometryComponents.empty()) {{\n"
        f"{indent}    {stream} << \"{{\\n  \\\"components\\\": [\\n\";\n"
        f"{indent}    {stream} << _RadAgentIrGeometryComponents();\n"
        f"{indent}    {stream} << \"  ]\\n}}\\n\";\n"
        f"{indent}    {stream}.close();\n"
        f"{indent}    return;\n"
        f"{indent}}}\n"
    )

    insertion_at = stream_match.end()
    open_check = re.search(
        rf"[ \t]*if\s*\(\s*!\s*{re.escape(stream)}\.is_open\s*\(\s*\)\s*\)\s*\{{",
        body[insertion_at:],
    )
    if open_check:
        if_start = insertion_at + open_check.start()
        block_open = body.find("{", if_start)
        block_close = _find_matching_brace(body, block_open) if block_open >= 0 else -1
        if block_close >= 0:
            insertion_at = block_close + 1
            if insertion_at < len(body) and body[insertion_at] == "\n":
                insertion_at += 1

    new_body = body[:insertion_at] + fallback + body[insertion_at:]
    return content[: open_brace + 1] + new_body + content[close_brace:]


def _replace_geometry_writer_with_ir_output(content: str, *, has_output_dir: bool = False) -> str:
    function_name = "OutputManager::WriteGeometryViewJson"
    start = content.find(function_name)
    if start < 0:
        return content
    open_brace = content.find("{", start)
    if open_brace < 0:
        return content
    close_brace = _find_matching_brace(content, open_brace)
    if close_brace < 0:
        return content
    stream_open = (
        "    std::string path = std::string(fOutputDir) + \"/geometry_view.json\";\n"
        "    std::ofstream ofs(path);\n"
        if has_output_dir
        else "    std::ofstream ofs(\"geometry_view.json\");\n"
    )
    replacement = (
        "{\n"
        f"{stream_open}"
        "    if (!ofs.is_open()) {\n"
        "        return;\n"
        "    }\n"
        "    ofs << \"{\\n  \\\"components\\\": [\\n\";\n"
        "    ofs << _RadAgentIrGeometryComponents();\n"
        "    ofs << \"  ]\\n}\\n\";\n"
        "    ofs.close();\n"
        "}\n"
    )
    return content[:open_brace] + replacement + content[close_brace + 1 :]


def _replace_inline_geometry_writer_with_ir_output(content: str) -> str:
    geometry_pos = content.find('"geometry_view.json"')
    if geometry_pos < 0:
        return content

    lines = content.splitlines(keepends=True)
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line)

    geometry_line = 0
    for index, start in enumerate(line_starts):
        end = start + len(lines[index])
        if start <= geometry_pos < end:
            geometry_line = index
            break

    open_line = -1
    for index in range(geometry_line, -1, -1):
        if lines[index].strip() == "{":
            open_line = index
            break
    if open_line < 0:
        return content

    close_line = _find_cpp_block_end_line(lines, open_line)
    if close_line < 0:
        return content

    block_lines = lines[open_line : close_line + 1]
    if not any('"geometry_view.json"' in line for line in block_lines):
        return content

    stream_line = ""
    stream_name = ""
    for line in block_lines:
        match = re.search(
            r"(?P<indent>[ \t]*)std::ofstream\s+(?P<stream>[A-Za-z_]\w*)\s*\([^;]*\"geometry_view\.json\"[^;]*\);\s*",
            line,
        )
        if match:
            stream_line = line
            stream_name = match.group("stream")
            break
    if not stream_line or not stream_name:
        return content

    block_indent = re.match(r"[ \t]*", lines[open_line]).group(0)
    body_indent = re.match(r"[ \t]*", stream_line).group(0)
    replacement = [
        lines[open_line],
        stream_line,
        f"{body_indent}if ({stream_name}.is_open()) {{\n",
        f"{body_indent}  {stream_name} << \"{{\\n  \\\"components\\\": [\\n\";\n",
        f"{body_indent}  {stream_name} << _RadAgentIrGeometryComponents();\n",
        f"{body_indent}  {stream_name} << \"  ]\\n}}\\n\";\n",
        f"{body_indent}}}\n",
        f"{block_indent}}}\n",
    ]
    return "".join(lines[:open_line] + replacement + lines[close_line + 1 :])


def _find_cpp_block_end_line(lines: list[str], open_line: int) -> int:
    depth = 0
    for index in range(open_line, len(lines)):
        depth += _brace_delta_outside_strings(lines[index])
        if index > open_line and depth == 0:
            return index
    return -1


def _brace_delta_outside_strings(line: str) -> int:
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        next_char = line[index + 1] if index + 1 < len(line) else ""
        if escaped:
            escaped = False
            index += 1
            continue
        if in_string:
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if in_char:
            if char == "\\":
                escaped = True
            elif char == "'":
                in_char = False
            index += 1
            continue
        if char == "/" and next_char == "/":
            break
        if char == '"':
            in_string = True
        elif char == "'":
            in_char = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    return depth


def _insert_after_include_block(content: str, insertion: str) -> str:
    lines = content.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#include "):
            insert_at = index + 1
            continue
        if stripped == "" and insert_at == index:
            insert_at = index + 1
            continue
        if insert_at:
            break
    lines.insert(insert_at, insertion.rstrip("\n"))
    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


def _find_matching_brace(content: str, open_brace: int) -> int:
    if open_brace < 0 or open_brace >= len(content) or content[open_brace] != "{":
        return -1
    depth = 0
    for index in range(open_brace, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _ir_geometry_components_for_output(g4_model_ir_subset: dict[str, Any]) -> list[dict[str, Any]]:
    raw_components = g4_model_ir_subset.get("components")
    if not isinstance(raw_components, list):
        return []
    unit_contract = _as_mapping(g4_model_ir_subset.get("unit_contract"))
    global_units = _as_mapping(g4_model_ir_subset.get("global_units"))
    length_unit = str(unit_contract.get("length_unit") or global_units.get("length") or "mm")
    coordinate_unit = str(unit_contract.get("coordinate_unit") or length_unit)
    length_factor = _length_unit_to_mm_factor(length_unit)
    coordinate_factor = _length_unit_to_mm_factor(coordinate_unit)

    components: list[dict[str, Any]] = []
    for index, raw_component in enumerate(raw_components):
        component = _as_mapping(raw_component)
        component_id = str(component.get("component_id") or component.get("id") or "").strip()
        if not component_id:
            continue
        placement = _as_mapping(component.get("placement"))
        roles = [str(role) for role in _as_list(component.get("roles"))]
        component_type = str(component.get("component_type") or "").strip()
        is_world = component_type == "world" or component_id.lower() == "world"
        components.append(
            {
                "id": component_id,
                "name": str(component.get("display_name") or component.get("name") or component_id),
                "shape": str(component.get("geometry_type") or component.get("shape") or "box"),
                "material": str(component.get("material_id") or component.get("material") or ""),
                "role": ",".join(roles) or component_type,
                "size_mm": _geometry_size_mm(
                    _as_mapping(component.get("dimensions")),
                    length_factor,
                ),
                "position_mm": _scaled_vector(
                    placement.get("position") or component.get("position"),
                    coordinate_factor,
                    [0.0, 0.0, 0.0],
                ),
                "rotation_deg": _scaled_vector(
                    placement.get("rotation") or component.get("rotation"),
                    1.0,
                    [0.0, 0.0, 0.0],
                ),
                "opacity": _geometry_opacity(component_id, component_type, roles, index),
            }
        )
    return components


def _geometry_size_mm(dimensions: dict[str, Any], factor: float) -> list[float]:
    radius = _dimension_radius(dimensions)
    if radius is not None:
        diameter = radius * 2.0 * factor
        return [
            diameter,
            diameter,
            _scaled_float(dimensions.get("dz") or dimensions.get("height"), factor, 1.0),
        ]
    if any(key in dimensions for key in ("dx", "dy", "dz")):
        return [
            _scaled_float(dimensions.get("dx"), factor, 1.0),
            _scaled_float(dimensions.get("dy"), factor, 1.0),
            _scaled_float(dimensions.get("dz"), factor, 1.0),
        ]
    return [
        _scaled_float(dimensions.get("x"), factor, 1.0),
        _scaled_float(dimensions.get("y"), factor, 1.0),
        _scaled_float(dimensions.get("z"), factor, 1.0),
    ]


def _dimension_radius(dimensions: dict[str, Any]) -> float | None:
    for key in ("r_outer", "rmax", "r_max", "radius", "r"):
        value = _float_or_none(dimensions.get(key))
        if value is not None:
            return value
    return None


def _geometry_opacity(
    component_id: str,
    component_type: str,
    roles: list[str],
    index: int,
) -> float:
    del index
    if component_id.lower() == "world" or component_type == "world":
        return 0.08
    role_text = ",".join(roles).lower()
    if "shield" in role_text or component_type == "shielding":
        return 0.32
    if "edep" in role_text or "dose" in role_text or "sensitive" in role_text:
        return 0.72
    if component_type in {"layer", "electrode"}:
        return 0.55
    return 0.44


def _scaled_vector(value: Any, factor: float, fallback: list[float]) -> list[float]:
    values = _as_list(value)
    if len(values) < 3:
        return list(fallback)
    return [
        _scaled_float(values[0], factor, fallback[0]),
        _scaled_float(values[1], factor, fallback[1]),
        _scaled_float(values[2], factor, fallback[2]),
    ]


def _scaled_float(value: Any, factor: float, fallback: float) -> float:
    parsed = _float_or_none(value)
    if parsed is None:
        return fallback
    return parsed * factor


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _length_unit_to_mm_factor(unit: str) -> float:
    normalized = unit.strip().lower()
    factors = {
        "mm": 1.0,
        "millimeter": 1.0,
        "millimeters": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "um": 1.0e-3,
        "µm": 1.0e-3,
        "micrometer": 1.0e-3,
        "micrometers": 1.0e-3,
        "nm": 1.0e-6,
    }
    return factors.get(normalized, 1.0)


def _insert_before_function_closing_brace(
    content: str,
    function_name: str,
    insertion: str,
) -> str:
    start = content.find(function_name)
    if start < 0:
        return content
    open_brace = content.find("{", start)
    if open_brace < 0:
        return content
    depth = 0
    close_index = -1
    for index in range(open_brace, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return content
    prefix = content[:close_index].rstrip() + "\n\n"
    suffix = content[close_index:]
    return prefix + insertion.rstrip() + "\n" + suffix


def _build_runtime_cpp_template_files(
    module_context: dict[str, Any],
    *,
    output_files: list[str],
    generated_by_path: dict[str, GeneratedModuleFile],
) -> list[GeneratedModuleFile]:
    del module_context
    content_by_path = _runtime_cpp_template_content_by_path(
        generated_by_path=generated_by_path,
    )
    return [
        GeneratedModuleFile(
            path=path,
            new_content=content_by_path[path],
            generated_by="runtime_app_cpp_template",
            module_name="runtime_app",
            rationale=(
                "Deterministic Geant4 application shell template used to keep "
                "main and CMake aligned with the RadAgent runtime contract."
            ),
            satisfies=["geant4 application entrypoint", "geant4 cmake build"],
        )
        for path in output_files
        if path in content_by_path
    ]


def _runtime_cpp_template_content_by_path(
    *,
    generated_by_path: dict[str, GeneratedModuleFile],
) -> dict[str, str]:
    action_header = generated_by_path.get("include/ActionInitialization.hh")
    action_header_content = action_header.new_content if action_header else ""
    uses_output_manager = _action_initialization_uses_output_manager(
        action_header_content
    )
    output_manager_include = ['#include "OutputManager.hh"'] if uses_output_manager else []
    output_manager_setup = (
        [
            "  auto* outputManager = new OutputManager();",
            "",
        ]
        if uses_output_manager
        else []
    )
    action_initialization = (
        "  runManager->SetUserInitialization(new ActionInitialization(detector, outputManager));"
        if uses_output_manager
        else "  runManager->SetUserInitialization(new ActionInitialization(detector));"
    )
    output_manager_teardown = ["  delete outputManager;"] if uses_output_manager else []
    return {
        "main.cc": "\n".join(
            [
                '#include "ActionInitialization.hh"',
                '#include "DetectorConstruction.hh"',
                *output_manager_include,
                '#include "PhysicsListFactoryWrapper.hh"',
                "",
                '#include "G4RunManager.hh"',
                '#include "G4UIExecutive.hh"',
                '#include "G4UImanager.hh"',
                '#include "G4VisExecutive.hh"',
                '#include "G4VModularPhysicsList.hh"',
                '#include "G4VUserPhysicsList.hh"',
                '#include "globals.hh"',
                "",
                "#include <cstdlib>",
                "#include <filesystem>",
                "#include <string>",
                "",
                "int main(int argc, char** argv) {",
                '  const char* outputEnv = std::getenv("G4_OUTPUT_DIR");',
                '  const std::string outputDir = (outputEnv && outputEnv[0] != \'\\0\') ? outputEnv : "output";',
                "  std::filesystem::create_directories(outputDir);",
                "",
                "  G4UIExecutive* ui = nullptr;",
                "  if (argc == 1) {",
                "    ui = new G4UIExecutive(argc, argv);",
                "  }",
                "",
                "  auto* runManager = new G4RunManager();",
                "  auto* detector = new DetectorConstruction();",
                "  runManager->SetUserInitialization(detector);",
                "",
                *output_manager_setup,
                "  PhysicsListFactoryWrapper physicsFactory;",
                "  runManager->SetUserInitialization(physicsFactory.CreatePhysicsList());",
                action_initialization,
                "",
                "  G4VisManager* visManager = nullptr;",
                "  if (ui) {",
                '    visManager = new G4VisExecutive("Quiet");',
                "    visManager->Initialize();",
                "  }",
                "",
                "  auto* uiManager = G4UImanager::GetUIpointer();",
                "  if (ui) {",
                '    uiManager->ApplyCommand("/control/execute macros/init_vis.mac");',
                "    if (ui->IsGUI()) {",
                '      uiManager->ApplyCommand("/control/execute macros/gui.mac");',
                "    }",
                "    ui->SessionStart();",
                "    delete ui;",
                "  } else {",
                '    const G4String command = "/control/execute ";',
                "    uiManager->ApplyCommand(command + argv[1]);",
                "  }",
                "",
                "  delete visManager;",
                *output_manager_teardown,
                "  delete runManager;",
                "  return 0;",
                "}",
                "",
            ]
        ),
        "CMakeLists.txt": RADAGENT_CMAKE_TEMPLATE,
    }


def _action_initialization_uses_output_manager(content: str) -> bool:
    return bool(
        re.search(
            r"ActionInitialization\s*\([^;{)]*DetectorConstruction\s*\*[^;{)]*,[^;{)]*OutputManager\s*\*",
            content,
            flags=re.DOTALL,
        )
    )


def _build_runtime_macro_files(
    module_context: dict[str, Any],
    *,
    output_files: list[str],
) -> list[GeneratedModuleFile]:
    events = resolve_self_check_events(
        g4_model_ir=module_context.get("g4_model_ir_subset"),
        task_spec=module_context.get("task_spec") or module_context.get("task"),
    )
    content_by_path = _runtime_macro_content_by_path(events=events)
    return [
        GeneratedModuleFile(
            path=path,
            new_content=content_by_path[path],
            generated_by="runtime_app_macro_template",
            module_name="runtime_app",
            rationale=(
                "Deterministic Geant4 macro template used to avoid unsupported "
                "command generation and extra model repair turns."
            ),
            satisfies=["runtime batch macro", "visual workbench macro"],
        )
        for path in output_files
        if path in content_by_path
    ]


def _runtime_macro_content_by_path(*, events: int) -> dict[str, str]:
    visual_events = VISUAL_WORKBENCH_EVENTS
    init_vis = "\n".join(
        [
            "# RadAgent Geant4 visual workbench initialization",
            "/control/verbose 2",
            "/control/saveHistory",
            "/run/verbose 2",
            "/run/setCut 0.1 mm",
            "/run/initialize",
            "/control/execute macros/vis.mac",
            "",
        ]
    )
    return {
        "macros/run.mac": "\n".join(
            [
                "# RadAgent Geant4 batch run",
                "/control/verbose 1",
                "/run/verbose 1",
                "/event/verbose 0",
                "/tracking/verbose 0",
                "/run/setCut 0.1 mm",
                "/run/initialize",
                f"/run/beamOn {events}",
                "",
            ]
        ),
        "macros/init.mac": init_vis,
        "macros/init_vis.mac": init_vis,
        "macros/vis.mac": "\n".join(
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
                f"/run/beamOn {visual_events}",
                "/vis/viewer/set/autoRefresh true",
                "/vis/verbose warnings",
                "/vis/viewer/flush",
                "",
            ]
        ),
        "macros/gui.mac": "\n".join(
            [
                "# RadAgent Geant4 visual workbench GUI controls",
                "/gui/addMenu file File",
                "/gui/addButton file Quit exit",
                "/gui/addMenu run Run",
                '/gui/addButton run "beamOn 1" "/run/beamOn 1"',
                f'/gui/addButton run "beamOn {visual_events}" "/run/beamOn {visual_events}"',
                "/gui/addMenu viewer Viewer",
                '/gui/addButton viewer "Set style surface" "/vis/viewer/set/style surface"',
                '/gui/addButton viewer "Set style wireframe" "/vis/viewer/set/style wireframe"',
                '/gui/addButton viewer "Refresh viewer" "/vis/viewer/refresh"',
                '/gui/addButton viewer "Flush viewer" "/vis/viewer/flush"',
                "",
            ]
        ),
    }


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
            "use them directly. existing_generated_file_summaries contains upstream "
            "module constructors/public methods extracted from generated headers; use "
            "those summaries as the cross-module API facts instead of spending a "
            "read_file turn before writing owned files."
        ),
    ]
    ctx["module_contract"] = contract
    ctx["runtime_app_file_group"] = {
        "name": group_name,
        "goal": group_goal,
        "output_files": output_files,
        "prior_files": prior_files,
    }
    ctx["agent_tool_policy"] = {"allow_read_file": False}
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
