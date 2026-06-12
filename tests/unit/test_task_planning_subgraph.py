"""Tests for Task Planning Subgraph."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_core.planning.nodes import parse_task, save_task_spec, validate_task_spec


@pytest.fixture
def temp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary workspace."""
    workspace = tmp_path / "sim_ws"
    workspace.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    return workspace


class TestParseTask:
    async def test_geant4_proton_query(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "模拟 10 MeV 质子垂直入射 300 微米硅片",
        }
        result = await parse_task(state)
        assert result["simulation_scope"] == ["geant4"]
        assert result["task_spec"]["particle"]["type"] == "proton"
        assert result["task_spec"]["energy"]["value"] == 10.0

    async def test_gamma_query(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "gamma irradiation of silicon detector at 1 MeV",
        }
        result = await parse_task(state)
        assert result["task_spec"]["particle"]["type"] == "gamma"

    async def test_simple_slab_query_normalizes_source_and_target(
        self,
        temp_workspace: Path,
    ) -> None:
        state = {
            "job_id": "test_job",
            "user_query": (
                "Build a minimal Geant4 silicon slab detector simulation: "
                "1 MeV electrons entering a 1 mm thick silicon slab in air, "
                "run 5 events, score total energy deposition per event, and "
                "write g4_summary.json, event_table.csv, edep_3d.csv, "
                "dose_3d.csv, and provenance.json. Keep geometry simple and "
                "use test mode."
            ),
        }

        result = await parse_task(state)

        particle = result["task_spec"]["particle"]
        assert particle["type"] == "electron"
        assert particle["energy_MeV"] == 1.0
        assert particle["energy_unit"] == "MeV"
        assert particle["events"] == 5
        target = result["task_spec"]["target"]
        assert target["material"] == "Silicon"
        assert target["geometry_type"] == "box"
        assert target["size_um"][2] == 1000.0
        assert set(result["task_spec"]["outputs"]) >= {
            "energy_deposition",
            "energy_deposition_map",
            "dose_distribution",
            "event_data",
        }
        from agent_core.schemas.task_spec import validate_task_spec

        _, errors = validate_task_spec(result["task_spec"])
        assert errors == []

    async def test_tcad_reserved_scope(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "simulate proton in silicon then TCAD analysis",
        }
        result = await parse_task(state)
        assert "tcad" in result["simulation_scope"]
        # TCAD keyword present → tcad detected. proton/silicon are not
        # geant4 scope keywords, so scope is ["tcad"] only.
        # This will be blocked by scope guard regardless.

    async def test_approved_ap8ae8_briefing_writes_particle_for_g4(
        self,
        temp_workspace: Path,
    ) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "仿真 500km 轨道 AP8 质子辐照硅探测器",
            "copilot_briefing": {
                "approved": True,
                "draft_plan": {
                    "space_radiation": {
                        "model": "AP8/AE8",
                        "particle": "proton",
                        "solar_period": "min",
                        "flux_mode": "integral",
                        "l_shell": 2.0,
                        "bb0": 1.05,
                        "events": 2500,
                        "source_id": "ap8_orbit_protons",
                    }
                },
            },
        }

        result = await parse_task(state)

        particle = result["task_spec"]["particles"][0]
        assert particle["source_id"] == "ap8_orbit_protons"
        assert particle["type"] == "proton"
        assert particle["energy_distribution"] == "spectrum"
        assert particle["generator_type"] == "gps"
        assert particle["events"] == 2500
        assert Path(particle["spectrum_file"]).is_file()
        assert "AP8/AE8 dataset" in particle["source_evidence"][0]
        external_source = result["task_spec"]["external_sources"][0]
        assert external_source["source_id"] == "ap8_orbit_protons"
        assert external_source["source_type"] == "environment"
        assert external_source["domain"] == "space_radiation"
        assert external_source["provider"] == "ap8ae8"
        assert external_source["model"] == "AP8MIN"
        assert external_source["status"] == "ready"
        assert particle["spectrum_file"] in external_source["artifact_paths"]
        assert external_source["parameters"]["flux_mode"] == "integral"
        assert external_source["consumers"] == [
            "task_planning",
            "g4_modeling",
            "g4_codegen",
            "gates",
            "copilot",
        ]

        saved = await save_task_spec(
            {
                "job_id": "test_job",
                "task_spec": result["task_spec"],
                "simulation_scope": result["simulation_scope"],
            }
        )
        saved_spec = json.loads(Path(saved["task_spec_path"]).read_text())
        assert saved_spec["particles"][0]["spectrum_file"] == particle["spectrum_file"]
        assert saved_spec["external_sources"][0]["artifact_paths"] == [
            particle["spectrum_file"]
        ]


class TestValidateTaskSpec:
    async def test_valid_spec(self) -> None:
        state = {
            "task_spec": {
                "simulation_scope": ["geant4"],
                "particle": {"type": "proton", "pdg_code": 2212},
            },
            "task_spec_errors": [],
        }
        result = await validate_task_spec(state)
        assert result["task_planning_status"] == "passed"

    async def test_invalid_spec(self) -> None:
        state = {
            "task_spec": {},
            "task_spec_errors": ["No particle type determined"],
        }
        result = await validate_task_spec(state)
        assert result["task_planning_status"] == "failed"


class TestSaveTaskSpec:
    async def test_saves_files(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "task_spec": {"simulation_scope": ["geant4"]},
            "simulation_scope": ["geant4"],
        }
        result = await save_task_spec(state)
        assert Path(result["task_spec_path"]).exists()
        saved = json.loads(Path(result["task_spec_path"]).read_text())
        assert saved["simulation_scope"] == ["geant4"]
