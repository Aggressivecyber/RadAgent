from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ShieldLayer:
    """单层屏蔽材料"""
    name: str                    # "外壳", "绝热层", "电子舱壁"
    material: str                # 用户输入: "铝合金", "polyethylene"
    geant4_material: str         # "G4_Al", "G4_POLYETHYLENE"
    density_g_cm3: float
    thickness_mm: float
    role: str = "shield"         # shield | insulation | structure | sensitive


@dataclass(frozen=True)
class ShieldGeometry:
    """多层堆叠结构（从外到内有序）"""
    name: str
    layers: tuple[ShieldLayer, ...]
    size_xy_cm: float = 10.0
    sensitive_volume: str = ""   # 敏感体积层名


@dataclass(frozen=True)
class OrbitEnvironment:
    """轨道辐射环境"""
    orbit_name: str              # LEO | MEO | GEO | HEO | 深空
    altitude_km: float
    inclination_deg: float = 0.0
    proton_flux_cm2_s: float = 0.0
    electron_flux_cm2_s: float = 0.0
    typical_energy_MeV: dict = field(default_factory=dict)  # {"proton": [10,400], ...}
    reference: str = ""


@dataclass(frozen=True)
class ParticleSource:
    """粒子源"""
    particle: str                # proton | electron | gamma | neutron | alpha
    energy_MeV: float | None = None
    energy_spectrum: tuple[float, ...] | None = None
    spectrum_probabilities: tuple[float, ...] | None = None
    source_type: str = "parallel_beam"  # parallel_beam | point | isotropic
    direction: tuple[float, float, float] = (0, 0, -1)


@dataclass(frozen=True)
class SimulationScenario:
    """单个仿真场景"""
    name: str = ""               # "LEO质子 100MeV"
    source: ParticleSource = field(default_factory=ParticleSource)
    num_events: int = 100000
    physics_list: str = "auto"


@dataclass(frozen=True)
class SimulationPlan:
    """完整仿真计划（调研子图输出）"""
    geometry: ShieldGeometry
    orbit: OrbitEnvironment | None = None
    scenarios: tuple[SimulationScenario, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class BuildResult:
    """Geant4 构建+运行结果"""
    source_dir: str = ""
    executable_path: str = ""
    compile_ok: bool = False
    compile_error: str = ""
    run_ok: bool = False
    run_stdout: str = ""
    run_stderr: str = ""


@dataclass(frozen=True)
class SimulationResult:
    """单场景仿真结果"""
    scenario_name: str = ""
    total_dose_Gy: float = 0.0
    dose_per_event_Gy: float = 0.0
    peak_layer: str = ""
    peak_depth_mm: float = 0.0
    penetrated: bool = False
    layer_doses: dict = field(default_factory=dict)  # {"外壳": 0.5, "绝热层": 0.3}
    num_events: int = 0
    raw_summary: str = ""


@dataclass(frozen=True)
class AnomalyCheck:
    status: str = "normal"
    details: str = ""


@dataclass(frozen=True)
class ControlState:
    retry_count: int = 0
    max_retries: int = 3
    approved: bool = False
