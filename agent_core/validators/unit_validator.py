"""Unit conversion and consistency validator for radiation simulation data."""

from __future__ import annotations

from typing import Tuple


class UnitValidator:
    """Validates and converts physical units used in simulation workflows."""

    KNOWN_UNITS: dict[str, list[str]] = {
        "energy": ["MeV", "keV", "GeV", "eV", "J"],
        "length": ["um", "mm", "cm", "m", "nm"],
        "dose": ["Gy", "kGy", "rad", "Mrad"],
        "time": ["s", "ms", "us", "ns", "ps"],
        "current": ["A", "mA", "uA", "nA", "pA"],
        "voltage": ["V", "mV", "kV"],
        "fluence": ["cm-2", "m-2"],
        "concentration": ["cm-3", "m-3"],
    }

    CONVERSION_FACTORS: dict[str, dict[str, float]] = {
        "energy": {"eV": 1.0, "keV": 1e3, "MeV": 1e6, "GeV": 1e9, "J": 6.242e18},
        "length": {"nm": 1.0, "um": 1e3, "mm": 1e6, "cm": 1e7, "m": 1e9},
        "dose": {"rad": 1.0, "Gy": 100.0, "kGy": 1e5, "Mrad": 1e6},
        "time": {"ps": 1.0, "ns": 1e3, "us": 1e6, "ms": 1e9, "s": 1e12},
        "current": {"pA": 1.0, "nA": 1e3, "uA": 1e6, "mA": 1e9, "A": 1e12},
        "voltage": {"mV": 1.0, "V": 1e3, "kV": 1e6},
        "fluence": {"cm-2": 1.0, "m-2": 1e-4},
        "concentration": {"cm-3": 1.0, "m-3": 1e-6},
    }

    def _find_category(self, unit: str) -> str | None:
        for category, units in self.KNOWN_UNITS.items():
            if unit in units:
                return category
        return None

    def validate_unit(
        self, value: float, unit: str, expected_units: list[str]
    ) -> Tuple[bool, str]:
        if unit in expected_units:
            return True, f"Unit '{unit}' is valid for value {value}."
        category = self._find_category(unit)
        if category is None:
            return False, f"Unknown unit '{unit}'."
        return (
            False,
            f"Unit '{unit}' not in expected {expected_units}. "
            f"Convertible within category '{category}'.",
        )

    def convert(
        self, value: float, from_unit: str, to_unit: str
    ) -> Tuple[float, bool]:
        cat = self._find_category(from_unit)
        if cat is None or self._find_category(to_unit) != cat:
            return 0.0, False
        factors = self.CONVERSION_FACTORS[cat]
        base_value = value * factors[from_unit]
        return base_value / factors[to_unit], True

    def check_consistency(
        self, data: dict, field_unit_map: dict[str, str]
    ) -> Tuple[bool, list[str]]:
        errors: list[str] = []
        for field, expected_unit in field_unit_map.items():
            if field not in data:
                errors.append(f"Missing field '{field}'.")
                continue
            entry = data[field]
            if not isinstance(entry, dict) or "value" not in entry or "unit" not in entry:
                errors.append(f"Field '{field}' must have 'value' and 'unit' keys.")
                continue
            unit = entry["unit"]
            cat = self._find_category(unit)
            expected_cat = self._find_category(expected_unit)
            if cat is None:
                errors.append(f"Unknown unit '{unit}' for field '{field}'.")
            elif cat != expected_cat:
                errors.append(
                    f"Unit '{unit}' ({cat}) incompatible with "
                    f"expected '{expected_unit}' ({expected_cat}) for '{field}'."
                )
        return len(errors) == 0, errors
