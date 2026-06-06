"""Physics sanity validator for simulation results."""

from __future__ import annotations

import math
from typing import Any

_VALID_PARTICLES = frozenset(
    "gamma electron positron proton neutron alpha mu- mu+ pi+ pi- pi0 "
    "kaon+ kaon- deuteron triton He3 GenericIon e- e+ anti_proton".split()
)


def _is_finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)
def _normalize(data: list[dict] | dict) -> list[dict]:
    return data if isinstance(data, list) else [data]


class PhysicsSanityValidator:
    """Validates physical plausibility of simulation output."""

    def validate_energy_deposition(self, edep_data: list[dict] | dict) -> tuple[bool, list[str]]:
        errors: list[str] = []
        total_edep = 0.0
        for i, row in enumerate(_normalize(edep_data)):
            edep = row.get("edep", row.get("energy_dep", row.get("energy")))
            if edep is None:
                errors.append(f"Row {i}: missing energy deposition field")
                continue
            if not _is_finite(edep):
                errors.append(f"Row {i}: energy is NaN or Inf ({edep})")
            elif edep < 0:
                errors.append(f"Row {i}: negative energy ({edep})")
            total_edep += edep if _is_finite(edep) else 0.0
        if total_edep <= 0 and not errors:
            errors.append("Total energy deposition is zero or negative with nonzero data")
        return (not errors, errors)

    def validate_dose(self, dose_data: list[dict] | dict) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for i, row in enumerate(_normalize(dose_data)):
            dose = row.get("dose", row.get("dose_Gy"))
            if dose is None:
                errors.append(f"Row {i}: missing dose field")
                continue
            if not _is_finite(dose):
                errors.append(f"Row {i}: dose is NaN or Inf ({dose})")
            elif dose < 0:
                errors.append(f"Row {i}: negative dose ({dose})")
        return (not errors, errors)

    def validate_event_data(self, event_data: list[dict]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not event_data:
            errors.append("Event data is empty (no events)")
            return (False, errors)
        for i, row in enumerate(event_data):
            for key, val in row.items():
                if isinstance(val, float) and not _is_finite(val):
                    errors.append(f"Event {i}.{key}: NaN or Inf")
            particle = row.get("particle", row.get("particle_type"))
            if particle is not None and str(particle) not in _VALID_PARTICLES:
                errors.append(f"Event {i}: unknown particle '{particle}'")
        return (not errors, errors)

    def validate_time_series(
        self, data: list[dict], time_field: str, value_field: str
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if len(data) < 2:
            errors.append("Time series requires at least 2 points")
            return (False, errors)
        for i, row in enumerate(data):
            t, v = row.get(time_field), row.get(value_field)
            if not _is_finite(t):
                errors.append(f"Point {i}: time is NaN/Inf")
            if not _is_finite(v):
                errors.append(f"Point {i}: value is NaN/Inf")
            if i > 0:
                prev_t = data[i - 1].get(time_field)
                if _is_finite(prev_t) and _is_finite(t) and t <= prev_t:
                    errors.append(f"Point {i}: time not monotonically increasing")
        return (not errors, errors)

    def validate_charge_integration(
        self, current_data: list[dict], time_field: str, current_field: str
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        ts_valid, ts_errors = self.validate_time_series(current_data, time_field, current_field)
        if not ts_valid:
            return (False, ts_errors)
        charge = 0.0
        for i in range(1, len(current_data)):
            dt = current_data[i][time_field] - current_data[i - 1][time_field]
            avg_i = 0.5 * (current_data[i][current_field] + current_data[i - 1][current_field])
            charge += avg_i * dt
        if charge == 0.0:
            errors.append("Integrated charge is zero")
        elif abs(charge) > 1e3:
            errors.append(f"Integrated charge suspiciously large ({charge:.3e} C)")
        return (not errors, errors)

    def validate_unit_traceability(
        self, data: dict, required_units: dict[str, str]
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        units = data.get("units", data.get("_units", {}))
        for field, expected in required_units.items():
            actual = units.get(field)
            if actual is None:
                errors.append(f"Field '{field}' has no declared unit (expected '{expected}')")
            elif actual != expected:
                errors.append(f"Field '{field}' unit mismatch: got '{actual}', expected '{expected}'")
        return (not errors, errors)

    def _run_single(self, fn_name: str, payload: Any, *args: str) -> list[str]:
        _, errs = getattr(self, fn_name)(payload, *args)
        return errs

    def run_all_checks(self, result_type: str, data: dict) -> tuple[bool, list[str]]:
        errors: list[str] = []
        checks: list[tuple[str, Any, ...]] = []
        if result_type == "g4":
            checks = [("validate_energy_deposition", data.get("edep")),
                      ("validate_dose", data.get("dose")),
                      ("validate_event_data", data.get("events"))]
        elif result_type == "tcad":
            checks = [("validate_dose", data.get("dose"))]
        elif result_type == "spice":
            checks = [("validate_time_series", data.get("time_series"), "time", "voltage"),
                      ("validate_charge_integration", data.get("current_data"), "time", "current")]
        for fn_name, payload, *extra in checks:
            if payload is not None:
                errors.extend(self._run_single(fn_name, payload, *extra))
        if "units" in data or "_units" in data:
            req = data.get("required_units", {})
            if req:
                errors.extend(self._run_single("validate_unit_traceability", data, req))
        return (not errors, errors)
