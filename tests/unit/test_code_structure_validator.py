from __future__ import annotations

from agent_core.validators.code_structure_validator import CodeStructureValidator


def test_geant4_project_accepts_runtime_manager_without_custom_physics_list(
    tmp_path,
) -> None:
    """Static gate should accept the current template's Geant4 physics ownership."""
    (tmp_path / "src").mkdir()
    (tmp_path / "include").mkdir()
    (tmp_path / "CMakeLists.txt").write_text(
        """
        cmake_minimum_required(VERSION 3.16)
        project(RadAgentG4)
        set(CMAKE_CXX_STANDARD 17)
        find_package(Geant4 REQUIRED)
        target_link_libraries(RadAgentG4 ${Geant4_LIBRARIES})
        """,
        encoding="utf-8",
    )
    (tmp_path / "include" / "DetectorConstruction.hh").write_text("", encoding="utf-8")
    (tmp_path / "include" / "PrimaryGeneratorAction.hh").write_text("", encoding="utf-8")
    (tmp_path / "include" / "SteppingAction.hh").write_text("", encoding="utf-8")
    (tmp_path / "src" / "DetectorConstruction.cc").write_text(
        "class DetectorConstruction {};",
        encoding="utf-8",
    )
    (tmp_path / "src" / "PrimaryGeneratorAction.cc").write_text(
        "class PrimaryGeneratorAction {};",
        encoding="utf-8",
    )
    (tmp_path / "src" / "SteppingAction.cc").write_text(
        "class SteppingAction {};",
        encoding="utf-8",
    )
    (tmp_path / "main.cc").write_text(
        """
        #include "QGSP_BIC_HP.hh"
        int main() {
          auto* physicsList = new QGSP_BIC_HP;
          runManager->SetUserInitialization(physicsList);
        }
        """,
        encoding="utf-8",
    )

    valid, errors = CodeStructureValidator().validate_geant4_project(str(tmp_path))

    assert valid
    assert "Missing required class: PhysicsList" not in errors


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
