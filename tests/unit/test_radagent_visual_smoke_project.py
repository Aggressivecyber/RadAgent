from __future__ import annotations

from pathlib import Path

from agent_core.tools.geant4_workbench import prepare_visual_workbench
from scripts.radagent_visual_smoke_project import create_radagent_visual_smoke_project


def test_radagent_visual_smoke_project_uses_external_incident_source(tmp_path: Path) -> None:
    project_dir = create_radagent_visual_smoke_project(tmp_path / "radagent_visual_smoke")

    primary = (project_dir / "src" / "PrimaryGeneratorAction.cc").read_text(encoding="utf-8")
    detector = (project_dir / "src" / "DetectorConstruction.cc").read_text(encoding="utf-8")
    run_macro = (project_dir / "macros" / "run.mac").read_text(encoding="utf-8")

    assert 'FindParticle("proton")' in primary
    assert "SetParticleEnergy(150.0 * MeV)" in primary
    assert "kSourceZ = -40.0 * mm" in primary
    assert "SetParticleMomentumDirection(G4ThreeVector(0.0, 0.0, 1.0))" in primary
    assert "External incident proton source" in primary
    assert "Thin entrance window" in detector
    assert "EntranceWindow" in detector
    assert "0.05 * mm" in detector
    assert "EntranceShield" not in detector
    assert "G4_Si" in detector
    assert "Device" in detector
    assert "/run/beamOn 1000" in run_macro
    assert "/vis/" not in run_macro


def test_radagent_visual_smoke_project_prepares_workbench_macros(tmp_path: Path) -> None:
    project_dir = create_radagent_visual_smoke_project(tmp_path / "radagent_visual_smoke")
    executable = project_dir / "build" / "radagent_visual_smoke"
    executable.parent.mkdir()
    executable.write_text("", encoding="utf-8")

    result = prepare_visual_workbench(project_dir, executable=executable, events=100)

    assert Path(result["init_macro"]).read_text(encoding="utf-8").strip().endswith(
        "/control/execute macros/vis.mac"
    )
    assert "/run/beamOn 100" in Path(result["vis_macro"]).read_text(encoding="utf-8")
    assert result["launch_command"] == [str(executable)]
