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

    async def test_tcad_reserved_scope(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test_job",
            "user_query": "simulate proton in silicon then TCAD analysis",
        }
        result = await parse_task(state)
        assert "tcad" in result["simulation_scope"]
        assert "geant4" in result["simulation_scope"]


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
