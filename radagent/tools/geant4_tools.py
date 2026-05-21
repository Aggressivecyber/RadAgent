"""Geant4 工具: 多层模板渲染、编译、运行、结果解析"""

import csv
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from string import Template

from radagent.config import CMAKE_TIMEOUT, GEANT4_SOURCE_SCRIPT, RUN_TIMEOUT, TEMPLATES_DIR, WORKSPACE_DIR
from radagent.schemas import BuildResult, ShieldGeometry, SimulationResult, SimulationScenario
from radagent.tools.knowledge import (
    generate_custom_material_cpp,
    generate_custom_particle_cpp,
    is_custom_material,
    is_custom_particle,
)

logger = logging.getLogger("radagent.node.tools")

# 物理列表映射
PHYSICS_MAP = {
    "QGSP_BIC": ("QGSP_BIC.hh", "QGSP_BIC"),
    "QGSP_BERT": ("QGSP_BERT.hh", "QGSP_BERT"),
    "QBBC": ("QBBC.hh", "QBBC"),
    "FTFP_BERT": ("FTFP_BERT.hh", "FTFP_BERT"),
    "QGSP_BIC_EMZ": ("QGSP_BIC_EMZ.hh", "QGSP_BIC_EMZ"),
    "QGSP_BIC_HP": ("QGSP_BIC_HP.hh", "QGSP_BIC_HP"),
    "QGSP_BIC_AllHP": ("QGSP_BIC_AllHP.hh", "QGSP_BIC_AllHP"),
}


def _make_project_dir(geometry: ShieldGeometry, scenario: SimulationScenario) -> Path:
    """在 workspace/ 下创建项目目录: YYYYMMDD_HHMMSS_意图描述"""
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 从几何名称和粒子信息生成简短目录名
    tag = geometry.name.replace(" ", "_")[:30]
    particle = scenario.source.particle
    energy = scenario.source.energy_MeV or 0
    dirname = f"{ts}_{tag}_{particle}{int(energy)}MeV"
    project_dir = WORKSPACE_DIR / dirname
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def render_multilayer_template(
    geometry: ShieldGeometry,
    scenario: SimulationScenario,
    work_dir: str | None = None,
) -> tuple[str, dict[str, str]]:
    """渲染多层屏蔽模板，返回 (输出目录, {文件名: 内容})"""
    template_dir = TEMPLATES_DIR / "multilayer_shield"
    if not template_dir.exists():
        logger.error("模板不存在: %s", template_dir)
        raise FileNotFoundError(f"模板不存在: {template_dir}")

    if work_dir:
        output_dir = Path(work_dir)
    else:
        output_dir = _make_project_dir(geometry, scenario)
    output_dir.mkdir(parents=True, exist_ok=True)

    layers = geometry.layers
    total_thickness_mm = sum(l.thickness_mm for l in layers)
    size_xy_cm = geometry.size_xy_cm
    logger.info("渲染模板: %d 层, 总厚度 %.2f mm, 横截面 %.1f cm",
                len(layers), total_thickness_mm, size_xy_cm)

    # 敏感体积层 — 用于计算剂量（需要质量）
    sensitive_layer = None
    for layer in layers:
        if layer.role == "sensitive" or layer.name == geometry.sensitive_volume:
            sensitive_layer = layer
            break
    if sensitive_layer is None:
        sensitive_layer = layers[-1]

    # 敏感体积质量 (kg): density_g_cm3 * (size_xy_cm * cm_to_m)^2 * (thickness_mm * mm_to_m)
    size_m = size_xy_cm * 0.01
    thick_m = sensitive_layer.thickness_mm * 0.001
    sensitive_mass_kg = sensitive_layer.density_g_cm3 * 1000 * size_m * size_m * thick_m

    # 自定义材料 C++ 代码
    custom_mat_names = set()
    for layer in layers:
        if is_custom_material(layer.geant4_material):
            custom_mat_names.add(layer.geant4_material)

    custom_mat_lines = []
    for mat_name in sorted(custom_mat_names):
        cpp_code = generate_custom_material_cpp(mat_name)
        if cpp_code:
            custom_mat_lines.append(cpp_code)
            logger.info("自定义材料: %s → C++ 定义已生成", mat_name)

    # 逐层厚度计算代码
    thickness_calc_lines = []
    for i, layer in enumerate(layers):
        thickness_calc_lines.append(
            f"  G4double thickness_{i} = {layer.thickness_mm} * mm;"
        )

    # 逐层构建代码
    layer_construction_lines = []
    for i, layer in enumerate(layers):
        safe_name = layer.name.replace(" ", "_").replace("（", "_").replace("）", "")
        mat = layer.geant4_material
        # 自定义材料用变量名，NIST 材料用 FindOrBuildMaterial
        if is_custom_material(mat):
            mat_expr = f"{mat}_mat"
        else:
            mat_expr = f'nist->FindOrBuildMaterial("{mat}")'
        layer_construction_lines.append(f'  {{')
        layer_construction_lines.append(f'    auto solid = new G4Box("{safe_name}", halfXY, halfXY, 0.5 * thickness_{i});')
        layer_construction_lines.append(f'    auto logic = new G4LogicalVolume(solid, {mat_expr}, "{safe_name}");')
        layer_construction_lines.append(f'    zOffset -= 0.5 * thickness_{i};')
        layer_construction_lines.append(f'    new G4PVPlacement(nullptr, G4ThreeVector(0, 0, zOffset), logic, "{safe_name}",')
        layer_construction_lines.append(f'                      logicWorld, false, 0, checkOverlaps);')
        layer_construction_lines.append(f'    zOffset -= 0.5 * thickness_{i};')
        if layer.role == "sensitive" or layer.name == geometry.sensitive_volume:
            layer_construction_lines.append(f'    fScoringVolume = logic;')
        layer_construction_lines.append(f'    fLayerVolumes.push_back(logic);')
        layer_construction_lines.append(f'  }}')
        layer_construction_lines.append(f'')

    # 逐层截断距离: cut = thickness / 4
    layer_cut_lines = []
    for i, layer in enumerate(layers):
        safe_name = layer.name.replace(" ", "_").replace("（", "_").replace("）", "")
        cut_mm = layer.thickness_mm / 4.0
        layer_cut_lines.append(f'  {{')
        layer_cut_lines.append(f'    auto region_{i} = new G4Region("{safe_name}_region");')
        layer_cut_lines.append(f'    auto cuts_{i} = new G4ProductionCuts();')
        layer_cut_lines.append(f'    cuts_{i}->SetProductionCut({cut_mm} * mm);')
        layer_cut_lines.append(f'    region_{i}->SetProductionCuts(cuts_{i});')
        layer_cut_lines.append(f'    fLayerVolumes[{i}]->SetRegion(region_{i});')
        layer_cut_lines.append(f'    region_{i}->AddRootLogicalVolume(fLayerVolumes[{i}]);')
        layer_cut_lines.append(f'  }}')

    # 物理列表
    pl = PHYSICS_MAP.get(scenario.physics_list, ("QBBC.hh", "QBBC"))

    # 粒子源
    source = scenario.source
    particle_type = _geant4_particle_name(source.particle)
    energy = source.energy_MeV if source.energy_MeV else 100.0
    direction = source.direction

    # 自定义粒子（离子）C++ 代码
    if is_custom_particle(source.particle):
        particle_def_code = generate_custom_particle_cpp(source.particle)
        logger.info("自定义粒子: %s → C++ 离子代码已生成", source.particle)
    else:
        particle_def_code = (
            f'  G4ParticleTable* particleTable = G4ParticleTable::GetParticleTable();\n'
            f'  G4String particleName;\n'
            f'  fParticleGun->SetParticleDefinition(particleTable->FindParticle(particleName = "{particle_type}"));'
        )

    subs = {
        "SIZE_XY": str(size_xy_cm),
        "TOTAL_THICKNESS_CALC": "\n".join(thickness_calc_lines),
        "TOTAL_THICKNESS_SUM": f"{total_thickness_mm} * mm",
        "CUSTOM_MATERIAL_DEFS": "\n".join(custom_mat_lines) if custom_mat_lines else "",
        "LAYER_CONSTRUCTION": "\n".join(layer_construction_lines),
        "LAYER_CUTS": "\n".join(layer_cut_lines),
        "SENSITIVE_MASS": str(sensitive_mass_kg),
        "PARTICLE_TYPE": particle_type,
        "PARTICLE_DEFINITION_CODE": particle_def_code,
        "PARTICLE_ENERGY": str(energy),
        "BEAM_DIRECTION_X": str(direction[0]),
        "BEAM_DIRECTION_Y": str(direction[1]),
        "BEAM_DIRECTION_Z": str(direction[2]),
        "NUM_EVENTS": str(scenario.num_events),
        "PHYSICS_LIST_INCLUDE": pl[0],
        "PHYSICS_LIST_CLASS": pl[1],
    }

    files = {}

    for src_file in template_dir.rglob("*"):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(template_dir)

        if src_file.suffix == ".tpl":
            content = src_file.read_text()
            rendered = Template(content).substitute(**subs)
            out_name = rel.with_suffix("")
            out_path = output_dir / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered)
            files[str(out_name)] = rendered
        else:
            out_path = output_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, out_path)
            files[str(rel)] = src_file.read_text()

    logger.info("模板渲染完成: %d 个文件写入 %s", len(files), output_dir)
    return str(output_dir), files


def build_geant4(source_dir: str) -> BuildResult:
    """编译 Geant4 工程: cmake + make"""
    build_dir = Path(source_dir) / "build"
    build_dir.mkdir(exist_ok=True)
    logger.info("开始编译: source_dir=%s", source_dir)

    try:
        cmake_result = subprocess.run(
            f"source {GEANT4_SOURCE_SCRIPT} && cd {build_dir} && cmake ..",
            shell=True, capture_output=True, text=True, timeout=CMAKE_TIMEOUT,
            executable="/bin/bash",
        )
        if cmake_result.returncode != 0:
            logger.error("cmake 失败 (rc=%d): %s", cmake_result.returncode, cmake_result.stderr[:500])
            return BuildResult(
                source_dir=source_dir, compile_ok=False,
                compile_error=cmake_result.stderr[-2000:],
            )

        make_result = subprocess.run(
            f"source {GEANT4_SOURCE_SCRIPT} && cd {build_dir} && make -j$(nproc)",
            shell=True, capture_output=True, text=True, timeout=CMAKE_TIMEOUT,
            executable="/bin/bash",
        )
        if make_result.returncode != 0:
            logger.error("make 失败 (rc=%d): %s", make_result.returncode, make_result.stderr[:500])
            return BuildResult(
                source_dir=source_dir, compile_ok=False,
                compile_error=make_result.stderr[-2000:],
            )

        executables = list(build_dir.glob("radg4_sim*"))
        if not executables:
            executables = [f for f in build_dir.iterdir()
                          if f.is_file() and f.stat().st_mode & 0o111]

        exe_path = str(executables[0]) if executables else ""
        logger.info("编译成功: %s", exe_path)

        return BuildResult(
            source_dir=source_dir, compile_ok=True,
            executable_path=exe_path,
        )

    except subprocess.TimeoutExpired:
        logger.error("编译超时 (%ds)", CMAKE_TIMEOUT)
        return BuildResult(source_dir=source_dir, compile_ok=False, compile_error="编译超时")
    except Exception as e:
        logger.error("编译异常: %s", e)
        return BuildResult(source_dir=source_dir, compile_ok=False, compile_error=str(e))


def _auto_thread_count() -> int:
    """自动检测 CPU 核心数并选择合理的线程数"""
    total = os.cpu_count() or 4
    if total <= 2:
        return total
    if total <= 8:
        return max(1, total - 1)
    return total - 2


def run_geant4(executable_path: str, num_events: int) -> BuildResult:
    """运行 Geant4 仿真（batch mode，多线程）"""
    if not executable_path or not Path(executable_path).exists():
        logger.error("可执行文件不存在: %s", executable_path)
        return BuildResult(run_ok=False, run_stderr=f"可执行文件不存在: {executable_path}")

    n_threads = _auto_thread_count()
    logger.info("CPU 核心数: %d, 使用线程数: %d", os.cpu_count() or 0, n_threads)

    macro_content = (
        f"/run/numberOfThreads {n_threads}\n"
        f"/run/initialize\n"
        f"/tracking/storeTrajectory 1\n"
        f"/run/beamOn {num_events}\n"
    )
    macro_path = Path(executable_path).parent / "run.mac"
    macro_path.write_text(macro_content)
    logger.info("运行仿真: %s, %d events", executable_path, num_events)

    try:
        result = subprocess.run(
            f"source {GEANT4_SOURCE_SCRIPT} && cd {Path(executable_path).parent} && {executable_path} run.mac",
            shell=True, capture_output=True, text=True, timeout=RUN_TIMEOUT,
            executable="/bin/bash",
        )
        ok = result.returncode == 0
        if ok:
            logger.info("仿真完成 (rc=0)")
        else:
            logger.error("仿真失败 (rc=%d): %s", result.returncode, result.stderr[:300])
        return BuildResult(
            run_ok=ok,
            run_stdout=result.stdout[-10000:],
            run_stderr=result.stderr[-2000:],
        )
    except subprocess.TimeoutExpired:
        logger.error("仿真超时 (%ds)", RUN_TIMEOUT)
        return BuildResult(run_ok=False, run_stderr="仿真运行超时")
    except Exception as e:
        logger.error("仿真异常: %s", e)
        return BuildResult(run_ok=False, run_stderr=str(e))


def parse_multilayer_output(
    stdout: str,
    layer_names: list[str],
    work_dir: str | None = None,
) -> SimulationResult:
    """解析多层 Geant4 输出。CSV 提供事件/步进级数据，stdout 提供剂量。"""
    if not work_dir or not stdout:
        return _parse_stdout_output(stdout, layer_names)

    logger.debug("尝试 CSV 解析: work_dir=%s", work_dir)
    csv_result = _parse_csv_output(work_dir, layer_names)
    if not csv_result or csv_result.num_events == 0:
        logger.debug("降级到 stdout 正则解析")
        return _parse_stdout_output(stdout, layer_names)

    # CSV 提供逐层数据 + 事件数；stdout 提供剂量（G4 直接计算，含质量）
    stdout_result = _parse_stdout_output(stdout, layer_names)
    logger.debug("合并结果: CSV(%d events) + stdout(%.4e Gy)",
                 csv_result.num_events, stdout_result.total_dose_Gy)

    return SimulationResult(
        total_dose_Gy=stdout_result.total_dose_Gy,
        dose_per_event_Gy=stdout_result.dose_per_event_Gy,
        peak_layer=csv_result.peak_layer or stdout_result.peak_layer,
        peak_depth_mm=csv_result.peak_depth_mm,
        penetrated=csv_result.penetrated,
        layer_doses=csv_result.layer_doses or stdout_result.layer_doses,
        num_events=csv_result.num_events,
        raw_summary=stdout[-2000:],
    )


def _parse_csv_output(work_dir: str, layer_names: list[str]) -> SimulationResult | None:
    """从 radagent_events.csv 和 radagent_steps.csv 解析结果"""
    wdir = Path(work_dir)
    events_csv = wdir / "radagent_events.csv"
    steps_csv = wdir / "radagent_steps.csv"

    if not events_csv.exists():
        return None

    MeV_to_J = 1.602e-13

    # 读取事件级数据
    events: list[dict] = []
    try:
        with events_csv.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                events.append(row)
    except Exception:
        return None

    num_events = len(events)
    if num_events == 0:
        return None

    total_edep_MeV = sum(float(e.get("total_edep_MeV", 0)) for e in events)
    total_edep_J = total_edep_MeV * MeV_to_J

    # 逐层能量沉积 — 从 steps CSV 按 volume 汇总
    layer_doses: dict[str, float] = {name: 0.0 for name in layer_names}
    penetrated = False

    if steps_csv.exists():
        try:
            with steps_csv.open(newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vol = row.get("volume", "")
                    edep = float(row.get("edep_MeV", 0)) * MeV_to_J
                    for name in layer_names:
                        safe_name = name.replace(" ", "_").replace("（", "_").replace("）", "")
                        if vol == safe_name:
                            layer_doses[name] += edep
                            break
        except Exception:
            pass

    # 判断是否穿透（有事件在最后一层之后仍 World 中有 step）
    if events and steps_csv.exists():
        last_layer = layer_names[-1] if layer_names else ""
        last_safe = last_layer.replace(" ", "_").replace("（", "_").replace("）", "")
        try:
            with steps_csv.open(newline="") as f:
                reader = csv.DictReader(f)
                last_event_id = events[-1].get("event_id", "")
                for row in reader:
                    if (row.get("event_id") == last_event_id
                            and row.get("volume") == "World"
                            and last_safe):
                        penetrated = True
                        break
        except Exception:
            pass

    # 峰值层
    peak_layer = ""
    peak_dose = 0.0
    for name, dose in layer_doses.items():
        if dose > peak_dose:
            peak_dose = dose
            peak_layer = name

    return SimulationResult(
        num_events=num_events,
        total_dose_Gy=0.0,       # 剂量需要质量信息，在 build_run 中计算
        dose_per_event_Gy=0.0,
        peak_layer=peak_layer,
        penetrated=penetrated,
        layer_doses=layer_doses,
    )


def _parse_stdout_output(stdout: str, layer_names: list[str]) -> SimulationResult:
    """从 stdout 正则解析结果（降级路径）"""
    if not stdout:
        return SimulationResult()

    unit_to_Gy = {
        "picoGy": 1e-12, "nanoGy": 1e-9, "microGy": 1e-6,
        "milliGy": 1e-3, "Gy": 1.0,
    }
    unit_to_J = {
        "eV": 1.602e-19, "keV": 1.602e-16, "MeV": 1.602e-13,
        "J": 1.0, "pJ": 1e-12, "nJ": 1e-9, "uJ": 1e-6,
    }

    total_dose_Gy = 0.0
    dose_match = re.search(
        r"敏感体积剂量:\s*([\d.eE+-]+)\s*(picoGy|nanoGy|microGy|milliGy|Gy)"
        r"\s*rms\s*=\s*([\d.eE+-]+)\s*(picoGy|nanoGy|microGy|milliGy|Gy)",
        stdout, re.IGNORECASE,
    )
    if dose_match:
        dose_val = float(dose_match.group(1))
        dose_unit = dose_match.group(2)
        total_dose_Gy = dose_val * unit_to_Gy.get(dose_unit, 1.0)

    num_events = 0
    event_match = re.search(r"总事件数:\s*(\d+)", stdout)
    if not event_match:
        event_match = re.search(r"run consists of\s+(\d+)", stdout, re.IGNORECASE)
    if event_match:
        num_events = int(event_match.group(1))

    dose_per_event = total_dose_Gy / num_events if num_events > 0 else 0.0

    layer_doses = {}
    layer_section = re.search(r"--- 逐层能量沉积 ---(.*)====", stdout, re.DOTALL)
    if layer_section:
        section_text = layer_section.group(1)
        for name in layer_names:
            safe_name = name.replace(" ", "_").replace("（", "_").replace("）", "")
            layer_match = re.search(
                rf"{re.escape(safe_name)}:\s*([\d.eE+-]+)\s*(\w+)",
                section_text,
            )
            if layer_match:
                val = float(layer_match.group(1))
                unit = layer_match.group(2)
                layer_doses[name] = val * unit_to_J.get(unit, 1.0)

    peak_layer = ""
    peak_dose = 0.0
    for name, dose in layer_doses.items():
        if dose > peak_dose:
            peak_dose = dose
            peak_layer = name

    return SimulationResult(
        total_dose_Gy=total_dose_Gy,
        dose_per_event_Gy=dose_per_event,
        peak_layer=peak_layer,
        penetrated=bool(layer_doses),
        layer_doses=layer_doses,
        num_events=num_events,
        raw_summary=stdout[-2000:],
    )


def _geant4_particle_name(particle: str) -> str:
    """将通用粒子名映射为 Geant4 粒子名"""
    mapping = {
        "proton": "proton",
        "e-": "e-",
        "electron": "e-",
        "e+": "e+",
        "positron": "e+",
        "gamma": "gamma",
        "neutron": "neutron",
        "alpha": "alpha",
        "pi+": "pi+",
        "pi-": "pi-",
        "mu-": "mu-",
        "mu+": "mu+",
        "deuteron": "deuteron",
        "triton": "triton",
        "He3": "He3",
        "ion": "alpha",
    }
    return mapping.get(particle, particle)
