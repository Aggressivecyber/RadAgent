"""Tests for the canonical Geant4 template project scaffold."""

from __future__ import annotations

import json
from pathlib import Path


def test_minimal_template_project_contains_stable_interfaces_and_contract(
    tmp_path: Path,
) -> None:
    from agent_core.g4_codegen.template_project import create_minimal_geant4_project

    project_dir = tmp_path / "geant4_project"

    manifest = create_minimal_geant4_project(project_dir, events=100)

    expected_files = {
        "CMakeLists.txt",
        "main.cc",
        "config/simulation_config.json",
        "include/ActionInitialization.hh",
        "include/DetectorConstruction.hh",
        "include/EventAction.hh",
        "include/Hit.hh",
        "include/MaterialRegistry.hh",
        "include/OutputManager.hh",
        "include/PrimaryGeneratorAction.hh",
        "include/RunAction.hh",
        "include/ScoringManager.hh",
        "include/SensitiveDetector.hh",
        "include/SteppingAction.hh",
        "src/ActionInitialization.cc",
        "src/DetectorConstruction.cc",
        "src/EventAction.cc",
        "src/Hit.cc",
        "src/MaterialRegistry.cc",
        "src/OutputManager.cc",
        "src/PrimaryGeneratorAction.cc",
        "src/RunAction.cc",
        "src/ScoringManager.cc",
        "src/SensitiveDetector.cc",
        "src/SteppingAction.cc",
        "macros/run.mac",
        "macros/radagent_self_check_100.mac",
    }

    assert set(manifest["files"]) >= expected_files
    for relative in expected_files:
        assert (project_dir / relative).is_file(), relative

    config = json.loads((project_dir / "config/simulation_config.json").read_text())
    assert config["template_version"] == manifest["template_version"]
    assert config["run"]["events"] == 100
    assert config["output_contract"] == [
        "g4_summary.json",
        "event_table.csv",
        "edep_3d.csv",
        "dose_3d.csv",
        "geometry_view.json",
        "particle_tracks.json",
        "energy_deposits.json",
        "provenance.json",
    ]

    action_header = (project_dir / "include/ActionInitialization.hh").read_text()
    assert "ActionInitialization(OutputManager* outputManager)" in action_header
    assert "Build() const override" in action_header

    main = (project_dir / "main.cc").read_text()
    assert "SetUserInitialization(new ActionInitialization(outputManager.get()))" in main
    assert "SetUserAction(new PrimaryGeneratorAction())" in (
        project_dir / "src/ActionInitialization.cc"
    ).read_text()

    output_source = (project_dir / "src/OutputManager.cc").read_text()
    for artifact in config["output_contract"]:
        assert artifact in output_source
    output_header = (project_dir / "include/OutputManager.hh").read_text()
    assert "struct GeometryDescription" in output_header
    assert "std::string shape" in output_header
    assert "SetGeometryDescription(" in output_source
    assert '\\"shape\\": \\"' in output_source
    assert '\\"shape\\": \\"box\\"' not in output_source

    run_macro = (project_dir / "macros/run.mac").read_text()
    assert "/run/beamOn 100" in run_macro


def test_minimal_template_project_includes_physics_and_tracking_limits(
    tmp_path: Path,
) -> None:
    from agent_core.g4_codegen.template_project import create_minimal_geant4_project

    project_dir = tmp_path / "geant4_project"

    create_minimal_geant4_project(project_dir, events=100)

    config = json.loads((project_dir / "config/simulation_config.json").read_text())
    assert config["physics"]["physics_list"] == "FTFP_BERT"
    assert config["physics"]["production_cuts_mm"]["gamma"] > 0
    assert config["physics"]["production_cuts_mm"]["electron"] > 0
    assert config["limits"]["detector_max_step_mm"] > 0
    assert config["limits"]["max_track_length_mm"] > config["limits"]["detector_max_step_mm"]
    assert config["limits"]["min_kinetic_energy_MeV"] > 0

    main = (project_dir / "main.cc").read_text()
    detector = (project_dir / "src/DetectorConstruction.cc").read_text()
    assert "SetDefaultCutValue" in main
    assert "CreateRunManager(G4RunManagerType::Serial)" in main
    assert "G4UserLimits" in detector
    assert "SetUserLimits" in detector

    forbidden_fill_tokens = ("TODO", "TBD", "PLACEHOLDER", "{{", "}}")
    for relative in create_minimal_geant4_project(project_dir, events=100)["files"]:
        content = (project_dir / relative).read_text(encoding="utf-8")
        assert not any(token in content for token in forbidden_fill_tokens), relative


def test_minimal_template_project_uses_runner_output_dir_and_single_edep_recorder(
    tmp_path: Path,
) -> None:
    from agent_core.g4_codegen.template_project import create_minimal_geant4_project

    project_dir = tmp_path / "geant4_project"

    create_minimal_geant4_project(project_dir, events=100)

    output_source = (project_dir / "src/OutputManager.cc").read_text()
    assert 'std::getenv("G4_OUTPUT_DIR")' in output_source
    assert "resolveOutputDirectory" in output_source

    stepping_source = (project_dir / "src/SteppingAction.cc").read_text()
    sensitive_source = (project_dir / "src/SensitiveDetector.cc").read_text()
    assert "RecordEnergyDeposit(" in stepping_source
    assert "RecordEnergyDeposit(" not in sensitive_source
    assert "single source" in sensitive_source


def test_minimal_template_project_preserves_existing_files_by_default(
    tmp_path: Path,
) -> None:
    from agent_core.g4_codegen.template_project import create_minimal_geant4_project

    project_dir = tmp_path / "geant4_project"
    project_dir.mkdir()
    main_path = project_dir / "main.cc"
    main_path.write_text("// existing generated project\n", encoding="utf-8")

    manifest = create_minimal_geant4_project(project_dir, events=100)

    assert main_path.read_text(encoding="utf-8") == "// existing generated project\n"
    assert "main.cc" in manifest["preserved_files"]
