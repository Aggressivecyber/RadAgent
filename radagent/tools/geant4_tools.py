"""Geant4 工具函数: 模板渲染、编译、运行、结果解析"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from string import Template

from radagent.config import CMAKE_TIMEOUT, GEANT4_SOURCE_SCRIPT, RUN_TIMEOUT, TEMPLATES_DIR
from radagent.schemas import BuildResult, SimulationParams, SimulationResult


def render_template(template_id: str, params: SimulationParams, work_dir: str | None = None) -> tuple[str, dict[str, str]]:
    """渲染 Geant4 模板，返回 (输出目录, {文件名: 内容})"""
    template_dir = TEMPLATES_DIR / template_id
    if not template_dir.exists():
        raise FileNotFoundError(f"模板不存在: {template_dir}")

    output_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="radagent_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    src_dir = output_dir / "src"
    include_dir = output_dir / "include"
    src_dir.mkdir(exist_ok=True)
    include_dir.mkdir(exist_ok=True)

    # 模板替换参数
    subs = {
        "TARGET_MATERIAL": params.material.geant4_name,
        "TARGET_THICKNESS": str(params.material.thickness_um),
        "TARGET_THICKNESS_UNIT": "um",
        "TARGET_THICKNESS_UNIT_STR": "um",
        "TARGET_SIZE_XY": str(params.material.size_xy_cm),
        "TARGET_SIZE_XY_UNIT": "cm",
        "TARGET_SIZE_XY_UNIT_STR": "cm",
        "PARTICLE_TYPE": params.particle.particle,
        "PARTICLE_ENERGY": str(params.particle.energy_MeV),
        "PARTICLE_ENERGY_UNIT": "MeV",
        "BEAM_DIRECTION_X": str(params.particle.direction[0]),
        "BEAM_DIRECTION_Y": str(params.particle.direction[1]),
        "BEAM_DIRECTION_Z": str(params.particle.direction[2]),
        "NUM_EVENTS": str(params.num_events),
    }

    # 物理列表映射
    physics_map = {
        "QGSP_BIC": ("QGSP_BIC.hh", "QGSP_BIC"),
        "QGSP_BERT": ("QGSP_BERT.hh", "QGSP_BERT"),
        "QBBC": ("QBBC.hh", "QBBC"),
        "FTFP_BERT": ("FTFP_BERT.hh", "FTFP_BERT"),
        "QGSP_BIC_EMZ": ("QGSP_BIC_EMZ.hh", "QGSP_BIC_EMZ"),
    }
    pl = physics_map.get(params.physics_list, ("QBBC.hh", "QBBC"))
    subs["PHYSICS_LIST_INCLUDE"] = pl[0]
    subs["PHYSICS_LIST_CLASS"] = pl[1]

    files = {}

    # 处理模板文件 (.tpl) 和固定文件
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

    return str(output_dir), files


def build_geant4(source_dir: str) -> BuildResult:
    """编译 Geant4 工程: cmake + make"""
    build_dir = Path(source_dir) / "build"
    build_dir.mkdir(exist_ok=True)

    try:
        cmake_result = subprocess.run(
            f"source {GEANT4_SOURCE_SCRIPT} && cd {build_dir} && cmake ..",
            shell=True, capture_output=True, text=True, timeout=CMAKE_TIMEOUT,
            executable="/bin/bash",
        )
        if cmake_result.returncode != 0:
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
            return BuildResult(
                source_dir=source_dir, compile_ok=False,
                compile_error=make_result.stderr[-2000:],
            )

        # 查找可执行文件
        executables = list(build_dir.glob("radg4_sim*")) + list(build_dir.glob("example*"))
        if not executables:
            executables = [f for f in build_dir.iterdir() if f.is_file() and f.stat().st_mode & 0o111]

        exe_path = str(executables[0]) if executables else ""

        return BuildResult(
            source_dir=source_dir, compile_ok=True,
            executable_path=exe_path,
        )

    except subprocess.TimeoutExpired:
        return BuildResult(source_dir=source_dir, compile_ok=False, compile_error="编译超时")
    except Exception as e:
        return BuildResult(source_dir=source_dir, compile_ok=False, compile_error=str(e))


def run_geant4(executable_path: str, num_events: int) -> BuildResult:
    """运行 Geant4 仿真（batch mode）"""
    if not executable_path or not Path(executable_path).exists():
        return BuildResult(run_ok=False, run_stderr=f"可执行文件不存在: {executable_path}")

    macro_content = f"/run/initialize\n/run/beamOn {num_events}\n"
    macro_path = Path(executable_path).parent / "run.mac"
    macro_path.write_text(macro_content)

    try:
        result = subprocess.run(
            f"source {GEANT4_SOURCE_SCRIPT} && cd {Path(executable_path).parent} && {executable_path} run.mac",
            shell=True, capture_output=True, text=True, timeout=RUN_TIMEOUT,
            executable="/bin/bash",
        )
        return BuildResult(
            run_ok=result.returncode == 0,
            run_stdout=result.stdout[-5000:],
            run_stderr=result.stderr[-2000:],
        )
    except subprocess.TimeoutExpired:
        return BuildResult(run_ok=False, run_stderr="仿真运行超时")
    except Exception as e:
        return BuildResult(run_ok=False, run_stderr=str(e))


def parse_geant4_output(stdout: str) -> SimulationResult:
    """解析 Geant4 B1 输出，提取剂量信息"""
    if not stdout:
        return SimulationResult()

    # B1 RunAction 输出格式:
    # "Cumulated dose per run, in scoring volume : 0.123 picoGy rms = 0.004 picoGy"
    total_dose_Gy = 0.0
    rms_dose_Gy = 0.0
    num_events = 0

    # 解析剂量 — G4BestUnit 可能输出 picoGy/nanoGy/microGy/milliGy/Gy
    unit_to_Gy = {
        "picoGy": 1e-12, "nanoGy": 1e-9, "microGy": 1e-6,
        "milliGy": 1e-3, "Gy": 1.0,
    }
    dose_match = re.search(
        r"Cumulated dose.*?:\s*([\d.eE+-]+)\s*(picoGy|nanoGy|microGy|milliGy|Gy)"
        r"\s*rms\s*=\s*([\d.eE+-]+)\s*(picoGy|nanoGy|microGy|milliGy|Gy)",
        stdout, re.IGNORECASE,
    )
    if dose_match:
        dose_val = float(dose_match.group(1))
        dose_unit = dose_match.group(2)
        rms_val = float(dose_match.group(3))
        rms_unit = dose_match.group(4)
        total_dose_Gy = dose_val * unit_to_Gy.get(dose_unit, 1.0)
        rms_dose_Gy = rms_val * unit_to_Gy.get(rms_unit, 1.0)

    # 解析事件数
    event_match = re.search(r"run consists of\s+(\d+)", stdout, re.IGNORECASE)
    if event_match:
        num_events = int(event_match.group(1))

    dose_per_event = total_dose_Gy / num_events if num_events > 0 else 0.0

    return SimulationResult(
        total_dose_Gy=total_dose_Gy,
        dose_per_event_Gy=dose_per_event,
        num_events=num_events,
        raw_summary=stdout[-1500:],
    )


def generate_macro(num_events: int) -> str:
    """生成 Geant4 macro 文件"""
    return f"/run/initialize\n/run/beamOn {num_events}\n"
