"""Geant4 output data contract — Pydantic v2 models.

Unified with parse_simulation_results output structure.
Every output file entry has: file, unit, exists, rows, checksum.
"""

from __future__ import annotations

from pydantic import BaseModel


class FileInfo(BaseModel):
    """Reference to a single output file."""

    file: str
    unit: str = ""
    exists: bool = False
    rows: int = 0
    checksum: str = ""


class G4ParticleInfo(BaseModel):
    type: str
    energy_MeV: float  # noqa: N815
    events: int


class G4GeometryInfo(BaseModel):
    target_material: str
    target_size_um: list[float]
    coordinate_unit: str = "um"


class G4OutputFiles(BaseModel):
    """All required Geant4 output files — must match parse_simulation_results."""

    edep: FileInfo
    dose: FileInfo
    event_table: FileInfo
    g4_summary: FileInfo
    provenance: FileInfo


class G4Checks(BaseModel):
    negative_energy_count: int = 0
    nan_count: int = 0
    total_events_recorded: int = 0


class G4OutputContract(BaseModel):
    """Top-level contract for Geant4 simulation outputs."""

    schema_version: str = "g4_output_v1"
    simulation_id: str
    particle: G4ParticleInfo | dict = {}
    geometry: G4GeometryInfo | dict = {}
    outputs: G4OutputFiles
    checks: G4Checks
    output_dir: str = ""
    all_required_files_present: bool = False
    provenance: dict = {}


class G4Provenance(BaseModel):
    """Reproducibility metadata for a Geant4 run."""

    simulation_id: str
    geant4_version: str
    physics_list: str
    random_seed: int
    generated_at: str
    code_hash: str


def validate_g4_output(
    data: dict,
) -> tuple[G4OutputContract | None, list[str]]:
    """Validate a raw dict against the G4OutputContract schema.

    Returns (contract, errors) — contract is None when validation fails.
    """
    try:
        contract = G4OutputContract.model_validate(data)
        return contract, []
    except Exception as exc:
        return None, [str(exc)]
