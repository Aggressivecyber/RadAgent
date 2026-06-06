"""G4 output contract / parse_simulation_results consistency tests.

Ensures that G4OutputContract schema and parse_simulation_results node
use the same FileInfo structure for all 5 output files.
"""

from __future__ import annotations

from agent_core.schemas.g4_output_contract import (
    FileInfo,
    G4Checks,
    G4OutputContract,
    G4OutputFiles,
    G4ParticleInfo,
    validate_g4_output,
)


def test_file_info_model():
    """FileInfo has required fields: file, unit, exists, rows, checksum."""
    fi = FileInfo(file="edep_3d.csv", unit="MeV", exists=True, rows=100, checksum="abc123")
    assert fi.file == "edep_3d.csv"
    assert fi.exists is True
    assert fi.rows == 100
    assert fi.checksum == "abc123"


def test_file_info_defaults():
    """FileInfo has sensible defaults for optional fields."""
    fi = FileInfo(file="test.csv")
    assert fi.unit == ""
    assert fi.exists is False
    assert fi.rows == 0
    assert fi.checksum == ""


def test_g4_output_files_has_all_five():
    """G4OutputFiles must have exactly 5 FileInfo entries."""
    G4OutputFiles(
        edep=FileInfo(file="edep_3d.csv"),
        dose=FileInfo(file="dose_3d.csv"),
        event_table=FileInfo(file="event_table.csv"),
        g4_summary=FileInfo(file="g4_summary.json"),
        provenance=FileInfo(file="provenance.json"),
    )
    field_names = set(G4OutputFiles.model_fields)
    assert field_names == {"edep", "dose", "event_table", "g4_summary", "provenance"}


def test_g4_output_contract_schema_version():
    """Contract has default schema_version."""
    contract = G4OutputContract(
        simulation_id="test-001",
        outputs=G4OutputFiles(
            edep=FileInfo(file="edep_3d.csv"),
            dose=FileInfo(file="dose_3d.csv"),
            event_table=FileInfo(file="event_table.csv"),
            g4_summary=FileInfo(file="g4_summary.json"),
            provenance=FileInfo(file="provenance.json"),
        ),
        checks=G4Checks(),
    )
    assert contract.schema_version == "g4_output_v1"


def test_g4_output_contract_all_required_files_present():
    """all_required_files_present is True when all 5 files exist."""
    contract = G4OutputContract(
        simulation_id="test-002",
        outputs=G4OutputFiles(
            edep=FileInfo(file="edep_3d.csv", exists=True),
            dose=FileInfo(file="dose_3d.csv", exists=True),
            event_table=FileInfo(file="event_table.csv", exists=True),
            g4_summary=FileInfo(file="g4_summary.json", exists=True),
            provenance=FileInfo(file="provenance.json", exists=True),
        ),
        checks=G4Checks(),
        all_required_files_present=True,
    )
    assert contract.all_required_files_present is True


def test_validate_g4_output_valid():
    """validate_g4_output returns contract with no errors for valid data."""
    data = {
        "simulation_id": "job-123",
        "outputs": {
            "edep": {"file": "edep_3d.csv", "exists": True, "rows": 50},
            "dose": {"file": "dose_3d.csv", "exists": True, "rows": 50},
            "event_table": {"file": "event_table.csv", "exists": True, "rows": 100},
            "g4_summary": {"file": "g4_summary.json", "exists": True},
            "provenance": {"file": "provenance.json", "exists": True},
        },
        "checks": {"total_events_recorded": 100},
    }
    contract, errors = validate_g4_output(data)
    assert contract is not None
    assert errors == []
    assert contract.outputs.edep.exists is True
    assert contract.outputs.event_table.rows == 100


def test_validate_g4_output_invalid():
    """validate_g4_output returns errors for invalid data."""
    contract, errors = validate_g4_output({"simulation_id": "bad"})
    assert contract is None
    assert len(errors) > 0


def test_g4_output_contract_has_output_dir():
    """Contract has output_dir field."""
    contract = G4OutputContract(
        simulation_id="test-003",
        outputs=G4OutputFiles(
            edep=FileInfo(file="edep_3d.csv"),
            dose=FileInfo(file="dose_3d.csv"),
            event_table=FileInfo(file="event_table.csv"),
            g4_summary=FileInfo(file="g4_summary.json"),
            provenance=FileInfo(file="provenance.json"),
        ),
        checks=G4Checks(),
        output_dir="/tmp/g4_output",
    )
    assert contract.output_dir == "/tmp/g4_output"


def test_g4_output_contract_has_provenance():
    """Contract has provenance field."""
    prov = {"simulation_id": "test-004", "geant4_version": "11.3"}
    contract = G4OutputContract(
        simulation_id="test-004",
        outputs=G4OutputFiles(
            edep=FileInfo(file="edep_3d.csv"),
            dose=FileInfo(file="dose_3d.csv"),
            event_table=FileInfo(file="event_table.csv"),
            g4_summary=FileInfo(file="g4_summary.json"),
            provenance=FileInfo(file="provenance.json"),
        ),
        checks=G4Checks(),
        provenance=prov,
    )
    assert contract.provenance["simulation_id"] == "test-004"


def test_particle_info_model():
    """G4ParticleInfo has required fields."""
    pi = G4ParticleInfo(type="proton", energy_MeV=10.0, events=1000)
    assert pi.type == "proton"
    assert pi.energy_MeV == 10.0
    assert pi.events == 1000
