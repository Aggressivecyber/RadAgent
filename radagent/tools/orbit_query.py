"""轨道辐射环境查询工具

读取预生成的 AE9/AP9 数据文件。文件格式为 SpacePy ae9ap9 输出的文本文件。

数据目录: radagent/data/
  按轨道类型组织:
    data/
    ├── LEO_500km_51.6deg/
    │   ├── pct50_proton_OMNI_00001.txt   # 质子通量
    │   └── pct50_electron_OMNI_00001.txt # 电子通量
    ├── GEO_35786km_0deg/
    └── ...

如需生成新轨道数据，访问 https://www.vdl.afrl.afmil/programs/ae9ap9/
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from radagent.config import DATA_DIR

logger = logging.getLogger("radagent.node.tools")

try:
    from spacepy import ae9ap9
    _SPACEPY_AVAILABLE = True
except ImportError:
    _SPACEPY_AVAILABLE = False


def query_radiation_environment(
    altitude_km: float,
    inclination_deg: float = 0.0,
    orbit_name: str = "",
) -> dict:
    """查询轨道辐射环境。

    优先读取预生成的 AE9/AP9 数据文件；
    文件不存在时返回基于轨道类型的典型通量估计。
    """
    logger.info("轨道查询: alt=%.1f km, inc=%.1f deg, name=%s",
                altitude_km, inclination_deg, orbit_name)

    # 1. 尝试从预生成文件读取
    orbit_dir = _find_orbit_dir(altitude_km, inclination_deg, orbit_name)
    if orbit_dir:
        result = _read_ae9ap9_files(orbit_dir, altitude_km, inclination_deg)
        if result:
            return result

    # 2. 无数据文件时返回典型通量估计
    logger.info("无预生成数据文件，使用轨道类型典型通量估计")
    return _estimate_flux(altitude_km, inclination_deg, orbit_name)


def _find_orbit_dir(altitude_km: float, inclination_deg: float,
                    orbit_name: str) -> Path | None:
    """在 DATA_DIR 中查找匹配的轨道数据目录。

    目录命名规则: {orbit_type}_{altitude}km_{inclination}deg
    模糊匹配：高度差 < 50km，倾角差 < 10deg
    """
    if not DATA_DIR.exists():
        return None

    best_dir = None
    best_diff = float("inf")

    for d in DATA_DIR.iterdir():
        if not d.is_dir():
            continue
        alt, inc = _parse_dir_name(d.name)
        if alt is None:
            continue
        diff = abs(alt - altitude_km) + abs(inc - inclination_deg) * 10
        if diff < best_diff:
            best_diff = diff
            best_dir = d

    # 高度差 < 50km 且倾角差 < 10deg 视为匹配
    if best_dir and best_diff < 150:
        logger.info("匹配轨道数据目录: %s", best_dir.name)
        return best_dir

    return None


def _parse_dir_name(name: str) -> tuple[float | None, float]:
    """从目录名解析高度和倾角。

    例: 'LEO_500km_51.6deg' → (500.0, 51.6)
    """
    alt_match = re.search(r"(\d+(?:\.\d+)?)\s*km", name)
    inc_match = re.search(r"(\d+(?:\.\d+)?)\s*deg", name)
    alt = float(alt_match.group(1)) if alt_match else None
    inc = float(inc_match.group(1)) if inc_match else 0.0
    return alt, inc


def _read_ae9ap9_files(orbit_dir: Path, altitude_km: float,
                       inclination_deg: float) -> dict | None:
    """读取 AE9/AP9 输出文件并提取通量信息。"""
    proton_files = sorted(orbit_dir.glob("*proton*"))
    electron_files = sorted(orbit_dir.glob("*electron*"))

    if not proton_files and not electron_files:
        logger.warning("目录 %s 中无 AE9/AP9 数据文件", orbit_dir)
        return None

    result: dict = {
        "orbit": {"altitude_km": altitude_km, "inclination_deg": inclination_deg},
        "model": "AE9/AP9",
        "reference": "Ginet et al., Space Weather, 2013",
        "data_source": str(orbit_dir),
    }

    # 用 SpacePy 读取（如果可用）
    if _SPACEPY_AVAILABLE:
        result.update(_read_with_spacepy(proton_files, electron_files))
    else:
        result.update(_read_raw_files(proton_files, electron_files))

    return result


def _read_with_spacepy(proton_files: list[Path],
                       electron_files: list[Path]) -> dict:
    """通过 SpacePy ae9ap9.readFile 读取数据文件。"""
    proton_info: dict = {}
    electron_info: dict = {}

    for f in proton_files[:1]:
        try:
            data = ae9ap9.readFile(str(f))
            flux_key = _find_flux_key(data)
            if flux_key:
                flux_vals = data[flux_key]
                import numpy as np
                proton_info = {
                    "integral_flux_cm2_s": float(np.mean(flux_vals)),
                    "peak_flux_cm2_s": float(np.max(flux_vals)),
                    "energy_range_MeV": _extract_energy_range(data),
                    "notes": f"AE9/AP9 质子通量 ({f.name})",
                }
                logger.info("SpacePy 读取质子数据: mean_flux=%.2e",
                            proton_info["integral_flux_cm2_s"])
        except Exception as e:
            logger.error("SpacePy 读取 %s 失败: %s", f.name, e)

    for f in electron_files[:1]:
        try:
            data = ae9ap9.readFile(str(f))
            flux_key = _find_flux_key(data)
            if flux_key:
                flux_vals = data[flux_key]
                import numpy as np
                electron_info = {
                    "integral_flux_cm2_s": float(np.mean(flux_vals)),
                    "peak_flux_cm2_s": float(np.max(flux_vals)),
                    "energy_range_MeV": _extract_energy_range(data),
                    "notes": f"AE9/AP9 电子通量 ({f.name})",
                }
                logger.info("SpacePy 读取电子数据: mean_flux=%.2e",
                            electron_info["integral_flux_cm2_s"])
        except Exception as e:
            logger.error("SpacePy 读取 %s 失败: %s", f.name, e)

    return {"proton": proton_info, "electron": electron_info}


def _find_flux_key(data) -> str | None:
    """在 SpacePy Ae9Data 对象中查找通量数据键。"""
    for key in data:
        if "flux" in key.lower() or "Flux" in key:
            return key
    # 降级：返回第一个非坐标非时间数组
    for key in data:
        val = data[key]
        if hasattr(val, "__len__") and len(val) > 0 and key not in ("Epoch", "Coords", "MJD", "posComp"):
            return key
    return None


def _extract_energy_range(data) -> list[float]:
    """从 AE9/AP9 数据中提取能量范围。"""
    for key in data:
        if "energy" in key.lower() or "Energy" in key:
            import numpy as np
            vals = data[key]
            if hasattr(vals, "__len__") and len(vals) > 0:
                arr = np.asarray(vals)
                return [float(arr.min()), float(arr.max())]
    return [1.0, 400.0]


def _read_raw_files(proton_files: list[Path],
                    electron_files: list[Path]) -> dict:
    """无 SpacePy 时直接解析 AE9/AP9 文本文件。"""
    proton_info: dict = {}
    electron_info: dict = {}

    for f in proton_files[:1]:
        try:
            proton_info = _parse_ae9ap9_text(f, "proton")
        except Exception as e:
            logger.error("解析 %s 失败: %s", f.name, e)

    for f in electron_files[:1]:
        try:
            electron_info = _parse_ae9ap9_text(f, "electron")
        except Exception as e:
            logger.error("解析 %s 失败: %s", f.name, e)

    return {"proton": proton_info, "electron": electron_info}


def _parse_ae9ap9_text(filepath: Path, species: str) -> dict:
    """解析 AE9/AP9 输出文本文件。

    文件格式: 头部带 # 注释，之后为列式数据。
    通常包含: 时间/位置坐标 + 通量列。
    """
    import numpy as np

    lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    header_lines = [l for l in lines if l.startswith("#")]

    # 找数据行（非注释、非空行）
    data_lines = [l for l in lines if l.strip() and not l.startswith("#")]
    if not data_lines:
        return {}

    # 解析数值数据
    rows = []
    for line in data_lines:
        try:
            vals = [float(x) for x in line.split()]
            rows.append(vals)
        except ValueError:
            continue

    if not rows:
        return {}

    arr = np.array(rows)
    # 最后一列通常是通量
    flux_col = arr[:, -1] if arr.shape[1] > 1 else arr[:, 0]

    # 从头部提取能量信息
    energy_range = _parse_energy_from_header(header_lines, species)

    return {
        "integral_flux_cm2_s": float(np.mean(flux_col)),
        "peak_flux_cm2_s": float(np.max(flux_col)),
        "energy_range_MeV": energy_range,
        "notes": f"AE9/AP9 {species} 通量 ({filepath.name})",
    }


def _parse_energy_from_header(header_lines: list[str], species: str) -> list[float]:
    """从 AE9/AP9 文件头部解析能量范围。"""
    for line in header_lines:
        # 常见格式: # Energy = 100.0 MeV 或 # E = [1.0, 400.0] MeV
        m = re.search(r"[Ee]nergy\s*=?\s*\[?([\d.]+)\s*,?\s*([\d.]*)\]?\s*([Mm][Ee][Vv])?", line)
        if m:
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            return [lo, hi if hi > lo else lo]

    # 默认值
    defaults = {"proton": [1.0, 400.0], "electron": [0.04, 7.0]}
    return defaults.get(species, [1.0, 100.0])


def _estimate_flux(altitude_km: float, inclination_deg: float,
                   orbit_name: str) -> dict:
    """基于轨道类型返回典型通量估计。

    数据来源: AE9/AP9 模型典型值 (Ginet et al., 2013)
    """
    orbit_type = _classify_orbit(altitude_km, orbit_name)

    # 典型通量值 (integral, cm^-2 s^-1)
    flux_data = {
        "LEO": {
            "proton": {
                "integral_flux_cm2_s": 5e4,
                "energy_range_MeV": [10, 400],
                "notes": "LEO 典型质子通量（南大西洋异常区）",
            },
            "electron": {
                "integral_flux_cm2_s": 1e6,
                "energy_range_MeV": [0.5, 7],
                "notes": "LEO 典型电子通量",
            },
        },
        "MEO": {
            "proton": {
                "integral_flux_cm2_s": 1e5,
                "energy_range_MeV": [10, 400],
                "notes": "MEO 质子通量（辐射带峰值区域）",
            },
            "electron": {
                "integral_flux_cm2_s": 1e7,
                "energy_range_MeV": [0.5, 7],
                "notes": "MEO 电子通量（外辐射带）",
            },
        },
        "GEO": {
            "proton": {
                "integral_flux_cm2_s": 1e3,
                "energy_range_MeV": [10, 400],
                "notes": "GEO 质子通量（太阳质子事件为主）",
            },
            "electron": {
                "integral_flux_cm2_s": 1e7,
                "energy_range_MeV": [0.04, 7],
                "notes": "GEO 电子通量（外辐射带外缘）",
            },
        },
        "HEO": {
            "proton": {
                "integral_flux_cm2_s": 5e5,
                "energy_range_MeV": [10, 400],
                "notes": "HEO 质子通量（穿越内外辐射带）",
            },
            "electron": {
                "integral_flux_cm2_s": 5e7,
                "energy_range_MeV": [0.5, 7],
                "notes": "HEO 电子通量",
            },
        },
    }

    default = {
        "proton": {
            "integral_flux_cm2_s": 5e4,
            "energy_range_MeV": [10, 400],
            "notes": "默认质子通量估计",
        },
        "electron": {
            "integral_flux_cm2_s": 1e6,
            "energy_range_MeV": [0.5, 7],
            "notes": "默认电子通量估计",
        },
    }

    data = flux_data.get(orbit_type, default)

    return {
        "orbit": {"altitude_km": altitude_km, "inclination_deg": inclination_deg},
        "model": f"AE9/AP9 典型值 ({orbit_type})",
        "reference": "Ginet et al., Space Weather, 2013",
        "data_source": "estimated",
        "proton": data["proton"],
        "electron": data["electron"],
    }


def _classify_orbit(altitude_km: float, orbit_name: str) -> str:
    """根据高度和名称判断轨道类型。"""
    name = orbit_name.upper()
    if "GEO" in name or "地球同步" in name:
        return "GEO"
    if "HEO" in name or "大椭圆" in name:
        return "HEO"
    if "MEO" in name or "中轨道" in name:
        return "MEO"
    if altitude_km > 30000:
        return "GEO"
    if altitude_km > 2000:
        return "MEO"
    return "LEO"
