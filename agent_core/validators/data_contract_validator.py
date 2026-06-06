"""Data contract validator for all simulation output packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent_core.schemas.g4_output_contract import G4OutputContract, G4Provenance
from agent_core.schemas.g4_to_tcad_contract import G4ToTCADContract
from agent_core.schemas.tcad_output_contract import TCADOutputContract
from agent_core.schemas.spice_output_contract import SPICEOutputContract


class DataContractValidator:
    """Validates simulation output dicts and directories against data contracts."""

    def validate_g4_output(self, data: dict) -> tuple[bool, list[str]]:
        try:
            G4OutputContract.model_validate(data)
            return True, []
        except Exception as exc:
            return False, [str(exc)]

    def validate_g4_to_tcad(self, data: dict) -> tuple[bool, list[str]]:
        errors: list[str] = []
        try:
            contract = G4ToTCADContract.model_validate(data)
        except Exception as exc:
            return False, [str(exc)]
        required_keys = {"g4_quantity", "tcad_parameter", "mapping_function",
                         "unit_conversion", "source_file"}
        for i, m in enumerate(contract.mappings):
            missing = required_keys - set(m.model_dump(exclude_none=True).keys())
            if missing:
                errors.append(f"mapping[{i}] missing fields: {sorted(missing)}")
        return (True, []) if not errors else (False, errors)

    def validate_tcad_output(self, data: dict) -> tuple[bool, list[str]]:
        try:
            TCADOutputContract.model_validate(data)
            return True, []
        except Exception as exc:
            return False, [str(exc)]

    def validate_spice_output(self, data: dict) -> tuple[bool, list[str]]:
        try:
            SPICEOutputContract.model_validate(data)
            return True, []
        except Exception as exc:
            return False, [str(exc)]

    def validate_provenance(self, provenance: dict) -> tuple[bool, list[str]]:
        required = {"simulation_id", "geant4_version", "physics_list",
                     "random_seed", "generated_at", "code_hash"}
        try:
            G4Provenance.model_validate(provenance)
            return True, []
        except Exception as exc:
            missing = required - set(provenance.keys())
            errors = [str(exc)]
            if missing:
                errors.append(f"Missing provenance fields: {sorted(missing)}")
            return False, errors

    def validate_data_package(
        self, package_dir: str, contract_type: str
    ) -> tuple[bool, list[str]]:
        validators = {
            "g4_output": self.validate_g4_output,
            "g4_to_tcad": self.validate_g4_to_tcad,
            "tcad_output": self.validate_tcad_output,
            "tcad_to_spice": self._validate_tcad_to_spice,
            "spice_output": self.validate_spice_output,
        }
        validator = validators.get(contract_type)
        if validator is None:
            return False, [f"Unknown contract type: {contract_type}"]

        pkg_path = Path(package_dir)
        if not pkg_path.is_dir():
            return False, [f"Package directory not found: {package_dir}"]

        all_errors: list[str] = []
        for fp in sorted(pkg_path.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                all_errors.append(f"{fp.name}: read/parse error: {exc}")
                continue
            _, errs = validator(data)
            all_errors.extend(f"{fp.name}: {e}" for e in errs)

        if not all_errors and not list(pkg_path.glob("*.json")):
            return False, ["No JSON files found in package directory"]
        return (True, []) if not all_errors else (False, all_errors)

    def _validate_tcad_to_spice(self, data: dict) -> tuple[bool, list[str]]:
        from agent_core.schemas.tcad_to_spice_contract import TCADToSPICEContract
        try:
            TCADToSPICEContract.model_validate(data)
            return True, []
        except Exception as exc:
            return False, [str(exc)]
