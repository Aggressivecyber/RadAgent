from __future__ import annotations

from agent_core.validators.code_structure_validator import CodeStructureValidator


def test_tcad_command_file_accepts_basic_sentaurus_structure() -> None:
    content = """
    File {
      Grid = "device.tdr"
      Plot = "result.tdr"
      Current = "iv.plt"
    }
    Electrode {
      { Name = "anode" Voltage = 0.0 }
      { Name = "cathode" Voltage = 1.0 }
    }
    Physics {
      Mobility(DopingDep)
      Recombination(SRH)
    }
    Solve {
      Poisson
      Coupled { Poisson Electron Hole }
    }
    """

    valid, errors = CodeStructureValidator().validate_tcad_command_file(content)

    assert valid
    assert errors == []


def test_tcad_command_file_rejects_empty_or_incomplete_content() -> None:
    valid, errors = CodeStructureValidator().validate_tcad_command_file(
        'File { Grid = "device.tdr" }'
    )

    assert not valid
    assert "Missing Electrode {...} block" in errors
    assert "Missing Physics {...} block" in errors
    assert "Missing Solve {...} block" in errors
    assert 'Missing File block plot = "..." reference' in errors
