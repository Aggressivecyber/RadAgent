"""轨道辐射环境查询工具

通过 SpacePy (AE9/AP9) 查询轨道辐射环境。SpacePy 不可用时直接报错。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("radagent.node.tools")

try:
    from spacepy import ae9ap9
    _SPACEPY_AVAILABLE = True
except ImportError:
    _SPACEPY_AVAILABLE = False


def query_radiation_environment(
    altitude_km: float,
    inclination_deg: float = 0.0,
    duration_years: float = 1.0,
    species: str = "both",
) -> dict:
    """查询轨道辐射环境（SpacePy AE9/AP9）"""
    if not _SPACEPY_AVAILABLE:
        raise RuntimeError(
            "SpacePy 未安装，无法查询轨道辐射环境。"
            "请安装: pip install spacepy"
            "并配置 IRENE AE9/AP9 数据库"
        )

    logger.info("SpacePy 查询: alt=%.1f km, inc=%.1f deg, dur=%.1f yr, species=%s",
                altitude_km, inclination_deg, duration_years, species)

    result = _query_via_spacepy(altitude_km, inclination_deg, duration_years, species)
    logger.info("SpacePy 查询成功: model=%s", result.get("model"))
    return result


def _query_via_spacepy(
    altitude_km: float,
    inclination_deg: float,
    duration_years: float,
    species: str,
) -> dict:
    """通过 SpacePy AE9/AP9 查询"""
    from spacepy import ae9ap9
    import numpy as np
    import tempfile

    work_dir = tempfile.mkdtemp(prefix="radagent_ae9ap9_")
    logger.debug("SpacePy 工作目录: %s", work_dir)

    n_orbits = int(duration_years * 365.25 * 24 * 3600 / (2 * np.pi * np.sqrt((6371 + altitude_km) ** 3 / 398600.4418)))
    n_points = min(n_orbits * 10, 10000)

    logger.debug("SpacePy 参数: n_orbits=%d, n_points=%d", n_orbits, n_points)

    ae9ap9._run_ae9ap9(
        webgui=False,
        specifyZenith=False,
        work_dir=work_dir,
        almond=[altitude_km, inclination_deg],
        model_type="ap9" if species in ("proton", "both") else "ae9",
        energy_indicies=None,
        flux_stat="mean",
        omnidirectional=True,
    )

    return {
        "orbit": {"altitude_km": altitude_km, "inclination_deg": inclination_deg},
        "model": "AE9/AP9 via SpacePy",
        "reference": "Ginet et al., Space Weather, 2013",
    }
