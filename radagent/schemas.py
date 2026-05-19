from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParticleSpec:
    particle: str
    energy_MeV: float
    direction: tuple[float, float, float] = (0, 0, 1)


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    geant4_name: str
    density_g_cm3: float
    thickness_um: float
    size_xy_cm: float = 2.0


@dataclass(frozen=True)
class SimulationParams:
    particle: ParticleSpec
    material: MaterialSpec
    num_events: int = 10000
    physics_list: str = "QGSP_BIC"


@dataclass(frozen=True)
class BuildResult:
    source_dir: str = ""
    executable_path: str = ""
    compile_ok: bool = False
    compile_error: str = ""
    run_ok: bool = False
    run_stdout: str = ""
    run_stderr: str = ""


@dataclass(frozen=True)
class SimulationResult:
    total_dose_Gy: float = 0.0
    dose_per_event_Gy: float = 0.0
    peak_depth_um: float = 0.0
    penetrated: bool = False
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
