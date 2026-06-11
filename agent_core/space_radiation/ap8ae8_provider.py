"""AP8/AE8 trapped-radiation source packaging for Geant4."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from knowledge_base.space_radiation.ap8ae8 import AP8AE8_DATASET_ID, AP8AE8_MODELS
from knowledge_base.space_radiation.paths import AP8AE8_DATA_ROOT

SolarPeriod = Literal["min", "max"]
FluxMode = Literal["integral", "differential"]


_ORBIT_RADIATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"AP[- ]?8|AE[- ]?8",
        r"Van Allen|trapped belt|radiation belt|orbit radiation",
        r"space[- ]?orbit|orbital radiation|L[- ]?shell",
        r"空间.*辐照|轨道.*辐照|轨道.*辐射|辐射带|范艾伦",
    )
)


@dataclass(frozen=True)
class OrbitRadiationRequest:
    """User-provided trapped-radiation environment request."""

    particle: str | None = None
    solar_period: SolarPeriod | None = None
    l_shell: float | None = None
    bb0: float | None = None
    altitude_km: float | None = None
    inclination_deg: float | None = None
    geodetic_samples: list[GeodeticOrbitSample] = field(default_factory=list)
    tle_lines: tuple[str, str] | None = None
    start_time: str | None = None
    stop_time: str | None = None
    sample_count: int = 1
    flux_mode: FluxMode = "differential"
    events: int = 1000
    source_id: str = "ap8ae8_trapped_radiation"


@dataclass(frozen=True)
class GeodeticOrbitSample:
    """One geodetic orbit sample for AP8/AE8 flux evaluation."""

    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    iso_time: str


@dataclass(frozen=True)
class OrbitRadiationValidation:
    """Validation result for a trapped-radiation request."""

    ready: bool
    missing_fields: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OrbitRadiationSourcePackage:
    """Geant4-facing AP8/AE8 source package."""

    request: OrbitRadiationRequest
    dataset_id: str
    model_name: str
    particle_type: str
    spectrum_file: Path
    evidence: list[str]

    def to_task_particle(self) -> dict:
        """Return a task particle dict that maps into existing SourceSpec logic."""
        return {
            "source_id": self.request.source_id,
            "type": self.particle_type,
            "energy_MeV": 1.0,
            "energy_unit": "MeV",
            "energy_distribution": "spectrum",
            "spectrum_file": str(self.spectrum_file),
            "direction": [0.0, 0.0, -1.0],
            "generator_type": "gps",
            "events": self.request.events,
            "source_evidence": self.evidence,
        }

    def to_external_source(self) -> dict:
        """Return the unified TaskSpec external source metadata."""
        return {
            "source_id": self.request.source_id,
            "source_type": "environment",
            "domain": "space_radiation",
            "provider": "ap8ae8",
            "model": self.model_name,
            "status": "ready",
            "artifact_paths": [str(self.spectrum_file)],
            "parameters": {
                "particle": self.request.particle,
                "solar_period": self.request.solar_period,
                "flux_mode": self.request.flux_mode,
                "l_shell": self.request.l_shell,
                "bb0": self.request.bb0,
                "events": self.request.events,
            },
            "provenance": {
                "dataset_id": self.dataset_id,
                "model": self.model_name,
            },
            "derived_outputs": [
                {
                    "kind": "geant4_source_spectrum",
                    "path": str(self.spectrum_file),
                    "consumer": "g4_modeling",
                }
            ],
            "limitations": ["AP8/AE8 is a static trapped-belt environment model."],
            "consumers": [
                "task_planning",
                "g4_modeling",
                "g4_codegen",
                "gates",
                "copilot",
            ],
            "evidence": self.evidence,
        }


class FluxEvaluator(Protocol):
    """Protocol for AP8/AE8 flux evaluators."""

    def flux(
        self,
        *,
        model_name: str,
        energy_mev: float,
        request: OrbitRadiationRequest,
    ) -> float:
        """Return flux for one energy in AP8/AE8 units."""


def is_orbit_radiation_request(text: str) -> bool:
    """Return true when text asks for an orbit trapped-radiation environment."""
    return any(pattern.search(text) for pattern in _ORBIT_RADIATION_PATTERNS)


class SpaceRadiationProvider:
    """Build AP8/AE8 source packages for Geant4 modeling."""

    def __init__(
        self,
        *,
        data_dir: Path = AP8AE8_DATA_ROOT,
        flux_evaluator: FluxEvaluator | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.flux_evaluator = flux_evaluator or AEP8RuntimeFluxEvaluator()

    def validate_request(self, request: OrbitRadiationRequest) -> OrbitRadiationValidation:
        """Check whether a request has enough data for this AP8/AE8 adapter."""
        missing: list[str] = []
        notes: list[str] = []
        if not request.particle:
            missing.append("particle")
        if not request.solar_period:
            missing.append("solar_period")
        has_geodetic = bool(request.geodetic_samples)
        has_tle = bool(request.tle_lines and request.start_time and request.stop_time)
        if request.l_shell is None and not has_geodetic and not has_tle:
            missing.append("l_shell")
        if request.bb0 is None and not has_geodetic and not has_tle:
            missing.append("bb0")
        if request.altitude_km is not None or request.inclination_deg is not None:
            notes.append(
                "altitude/inclination are useful briefing inputs, but this adapter "
                "requires L-shell and B/B0 until an orbit/magnetic-field adapter is added."
            )
        return OrbitRadiationValidation(ready=not missing, missing_fields=missing, notes=notes)

    def select_model(self, request: OrbitRadiationRequest) -> str:
        """Select AP8/AE8 model name from particle and solar period."""
        particle = _normalize_particle(request.particle)
        if request.solar_period not in {"min", "max"}:
            raise ValueError("solar_period must be 'min' or 'max'")
        if particle == "proton":
            return "AP8MIN" if request.solar_period == "min" else "AP8MAX"
        if particle == "e-":
            return "AE8MIN" if request.solar_period == "min" else "AE8MAX"
        raise ValueError("particle must be proton or electron/e- for AP8/AE8")

    def create_source_package(
        self,
        request: OrbitRadiationRequest,
        *,
        output_dir: Path,
    ) -> OrbitRadiationSourcePackage:
        """Create an AP8/AE8-derived source package and spectrum CSV."""
        validation = self.validate_request(request)
        if not validation.ready:
            missing = ", ".join(validation.missing_fields)
            raise ValueError(f"missing AP8/AE8 request fields: {missing}")
        model_name = self.select_model(request)
        particle_type = _normalize_particle(request.particle)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        spectrum_file = output_dir / f"{request.source_id}_{model_name.lower()}_spectrum.csv"
        _write_evaluated_spectrum(
            spectrum_file,
            model_name=model_name,
            request=request,
            evaluator=self.flux_evaluator,
        )
        model = AP8AE8_MODELS[model_name]
        evidence = [
            f"AP8/AE8 dataset {AP8AE8_DATASET_ID} model {model_name} file {model['file']}",
            _environment_evidence(request),
            f"solar_period={request.solar_period} flux_mode={request.flux_mode}",
        ]
        return OrbitRadiationSourcePackage(
            request=request,
            dataset_id=AP8AE8_DATASET_ID,
            model_name=model_name,
            particle_type=particle_type,
            spectrum_file=spectrum_file,
            evidence=evidence,
        )


def _normalize_particle(particle: str | None) -> str:
    value = (particle or "").strip().lower()
    if value in {"p", "proton", "protons", "质子"}:
        return "proton"
    if value in {"electron", "electrons", "e", "e-", "电子"}:
        return "e-"
    return value


def _write_evaluated_spectrum(
    path: Path,
    *,
    model_name: str,
    request: OrbitRadiationRequest,
    evaluator: FluxEvaluator,
) -> None:
    """Write AP8/AE8 evaluated spectrum from the runtime model."""
    particle_type = _normalize_particle(request.particle)
    energies = _energy_grid_mev(particle_type)
    lines = ["energy_MeV,flux_cm-2_s-1_MeV-1"]
    for energy in energies:
        flux = evaluator.flux(
            model_name=model_name,
            energy_mev=energy,
            request=request,
        )
        lines.append(f"{energy:.6g},{flux:.6g}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class AEP8RuntimeFluxEvaluator:
    """Runtime AP8/AE8 evaluator backed by the `aep8` and `astropy` packages."""

    def flux(
        self,
        *,
        model_name: str,
        energy_mev: float,
        request: OrbitRadiationRequest,
    ) -> float:
        try:
            import aep8
            from astropy import units as u
            from astropy.coordinates import EarthLocation
            from astropy.time import Time
        except ImportError as exc:
            raise RuntimeError(
                "AP8/AE8 orbit flux evaluation requires dependencies: "
                "aep8, astropy, skyfield, sgp4. Install RadAgent project dependencies."
            ) from exc

        particle, solar = _aep8_particle_and_solar(model_name)
        model = aep8.model(particle=particle, solar=solar)
        energy = energy_mev * u.MeV
        if request.l_shell is not None and request.bb0 is not None:
            if request.flux_mode == "integral":
                flux = model.integral_flux_for_geomagnetic_coordinates(
                    request.l_shell,
                    request.bb0,
                    energy,
                )
            else:
                flux = model.differential_flux_for_geomagnetic_coordinates(
                    request.l_shell,
                    request.bb0,
                    energy,
                )
            return float(flux.value)

        samples = request.geodetic_samples or _tle_to_geodetic_samples(request)
        if not samples:
            raise ValueError(
                "AP8/AE8 request needs magnetic coordinates, geodetic samples, or TLE"
            )

        values: list[float] = []
        for sample in samples:
            location = EarthLocation(
                lat=sample.latitude_deg * u.deg,
                lon=sample.longitude_deg * u.deg,
                height=sample.altitude_km * u.km,
            )
            time = Time(sample.iso_time)
            if request.flux_mode == "integral":
                flux = model.integral_flux(location, time, energy)
            else:
                flux = model.differential_flux(location, time, energy)
            values.append(float(flux.value))
        return sum(values) / len(values)


def _energy_grid_mev(particle_type: str) -> tuple[float, ...]:
    if particle_type == "proton":
        return (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 100.0, 400.0)
    return (0.04, 0.1, 0.5, 1.0, 2.0, 4.0, 7.0)


def _aep8_particle_and_solar(model_name: str) -> tuple[str, str]:
    model = model_name.upper()
    if model == "AP8MIN":
        return "p", "min"
    if model == "AP8MAX":
        return "p", "max"
    if model == "AE8MIN":
        return "e", "min"
    if model == "AE8MAX":
        return "e", "max"
    raise ValueError(f"unsupported AP8/AE8 model: {model_name}")


def _environment_evidence(request: OrbitRadiationRequest) -> str:
    if request.l_shell is not None and request.bb0 is not None:
        return f"magnetic coordinates L={request.l_shell} B/B0={request.bb0}"
    if request.geodetic_samples:
        return f"geodetic orbit samples={len(request.geodetic_samples)}"
    if request.tle_lines:
        return (
            "TLE orbit sample "
            f"start={request.start_time} stop={request.stop_time} count={request.sample_count}"
        )
    return "orbit environment unresolved"


def _tle_to_geodetic_samples(request: OrbitRadiationRequest) -> list[GeodeticOrbitSample]:
    if not request.tle_lines or not request.start_time or not request.stop_time:
        return []
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ImportError as exc:
        raise RuntimeError(
            "TLE orbit sampling requires dependencies: skyfield and sgp4."
        ) from exc

    line1, line2 = request.tle_lines
    satellite = EarthSatellite(line1, line2, "RADAGENT_ORBIT", load.timescale())
    start = _parse_utc(request.start_time)
    stop = _parse_utc(request.stop_time)
    count = max(int(request.sample_count), 1)
    if count == 1:
        datetimes = [start]
    else:
        span = (stop - start).total_seconds()
        datetimes = [
            datetime.fromtimestamp(
                start.timestamp() + span * index / (count - 1),
                tz=UTC,
            )
            for index in range(count)
        ]
    ts = load.timescale()
    samples: list[GeodeticOrbitSample] = []
    for item in datetimes:
        geocentric = satellite.at(ts.from_datetime(item))
        subpoint = wgs84.subpoint(geocentric)
        samples.append(
            GeodeticOrbitSample(
                latitude_deg=float(subpoint.latitude.degrees),
                longitude_deg=float(subpoint.longitude.degrees),
                altitude_km=float(subpoint.elevation.km),
                iso_time=item.isoformat().replace("+00:00", "Z"),
            )
        )
    return samples


def _parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
