"""Tests for MVP-1 scope guard — write_code_patch blocks TCAD/SPICE."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from agent_core.nodes.generate_report import generate_report
from agent_core.nodes.write_code_patch import write_code_patch


def _make_state(
    simulation_scope: list[str] | None = None,
    job_id: str = "scope-test",
) -> dict:
    """Build a minimal state dict with given simulation_scope."""
    return {
        "job_id": job_id,
        "task_spec": {
            "simulation_scope": simulation_scope or ["geant4"],
            "particle": {"type": "proton", "energy_MeV": 10.0},
        },
        "simulation_ir": {
            "g4_config": {
                "particle_source": {"type": "proton", "energy": "10 MeV"},
                "geometry": {"detector": "silicon"},
            },
        },
        "g4_context": [],
    }


class TestScopeGuardBlocksTCAD:
    """TCAD in simulation_scope → write_code_patch must block."""

    @pytest.mark.asyncio
    async def test_tcad_blocked(self) -> None:
        state = _make_state(simulation_scope=["geant4", "tcad"])
        result = await write_code_patch(state)
        assert result["proposed_patch"] == {}
        assert any("MVP-1 Scope Guard" in e for e in result.get("errors", []))
        assert any("tcad" in e.lower() for e in result.get("errors", []))

    @pytest.mark.asyncio
    async def test_tcad_only_blocked(self) -> None:
        state = _make_state(simulation_scope=["tcad"])
        result = await write_code_patch(state)
        assert result["proposed_patch"] == {}
        assert any("MVP-1 Scope Guard" in e for e in result.get("errors", []))


class TestScopeGuardBlocksSPICE:
    """SPICE in simulation_scope → write_code_patch must block."""

    @pytest.mark.asyncio
    async def test_spice_blocked(self) -> None:
        state = _make_state(simulation_scope=["geant4", "spice"])
        result = await write_code_patch(state)
        assert result["proposed_patch"] == {}
        assert any("spice" in e.lower() for e in result.get("errors", []))

    @pytest.mark.asyncio
    async def test_spice_only_blocked(self) -> None:
        state = _make_state(simulation_scope=["spice"])
        result = await write_code_patch(state)
        assert result["proposed_patch"] == {}
        assert any("MVP-1 Scope Guard" in e for e in result.get("errors", []))


class TestScopeGuardBlocksBoth:
    """TCAD + SPICE in simulation_scope → blocks both."""

    @pytest.mark.asyncio
    async def test_tcad_and_spice_blocked(self) -> None:
        state = _make_state(simulation_scope=["geant4", "tcad", "spice"])
        result = await write_code_patch(state)
        assert result["proposed_patch"] == {}
        errors = result.get("errors", [])
        assert len(errors) >= 1
        err_text = " ".join(errors).lower()
        assert "tcad" in err_text
        assert "spice" in err_text


class TestScopeGuardAllowsGeant4:
    """Geant4-only scope → write_code_patch proceeds (may fail on LLM, but not blocked)."""

    @pytest.mark.asyncio
    async def test_geant4_only_not_blocked(self, tmp_path: Path) -> None:
        state = _make_state(simulation_scope=["geant4"])
        # Mock LLM to avoid actual API call — ainvoke is async
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "files": {"geant4_sim.cc": "int main() { return 0; }"},
            "description": "stub",
            "assumptions": [],
        })
        mock_llm = MagicMock()
        mock_llm.ainvoke = MagicMock(return_value=mock_response)
        # Make ainvoke awaitable (AsyncMock)
        from unittest.mock import AsyncMock
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        # Create job dir subdirectories that write_code_patch expects
        (tmp_path / "04_generated_code").mkdir(parents=True, exist_ok=True)

        with (
            patch("agent_core.llm.get_llm", return_value=mock_llm),
            patch("agent_core.nodes.write_code_patch.get_output_dir", return_value=tmp_path),
            patch("agent_core.nodes.write_code_patch.get_job_dir", return_value=tmp_path),
        ):
            result = await write_code_patch(state)

        # Should NOT have scope guard errors
        errors = result.get("errors", [])
        assert not any("MVP-1 Scope Guard" in e for e in errors)
        # Should have a non-empty patch (LLM returned files)
        assert result.get("proposed_patch", {}) != {}


class TestReportScopeDeclaration:
    """generate_report includes scope declaration for TCAD/SPICE."""

    @pytest.mark.asyncio
    async def test_report_mentions_tcad_reserved(self, tmp_path: Path) -> None:
        state = {
            "job_id": "rpt-scope",
            "user_query": "test",
            "task_spec": {
                "simulation_scope": ["geant4", "tcad"],
                "particle": {"type": "proton"},
            },
            "rag_required_sources": ["geant4"],
            "rag_optional_sources": [],
            "rag_sufficiency_score": 0.0,
            "rag_sufficiency_report": {},
            "proposed_patch": {},
            "gate_results": [],
            "simulation_results": {},
            "data_contract_results": {},
            "failure_report": {},
            "execution_mode": "dev_no_geant4_env",
            "skipped_gates": [],
            "context_decision": "block_no_context",
            "web_context": [],
        }
        with patch("agent_core.nodes.generate_report.get_job_dir", return_value=tmp_path):
            (tmp_path / "10_report").mkdir(parents=True, exist_ok=True)
            result = await generate_report(state)
        report = result["final_report"]
        assert "reserved for later mvp" in report.lower()
        assert "tcad" in report.lower()

    @pytest.mark.asyncio
    async def test_report_mentions_spice_reserved(self, tmp_path: Path) -> None:
        state = {
            "job_id": "rpt-scope2",
            "user_query": "test",
            "task_spec": {
                "simulation_scope": ["spice"],
                "particle": {"type": "proton"},
            },
            "rag_required_sources": [],
            "rag_optional_sources": [],
            "rag_sufficiency_score": 0.0,
            "rag_sufficiency_report": {},
            "proposed_patch": {},
            "gate_results": [],
            "simulation_results": {},
            "data_contract_results": {},
            "failure_report": {},
            "execution_mode": "dev_no_geant4_env",
            "skipped_gates": [],
            "context_decision": "block_no_context",
            "web_context": [],
        }
        with patch("agent_core.nodes.generate_report.get_job_dir", return_value=tmp_path):
            (tmp_path / "10_report").mkdir(parents=True, exist_ok=True)
            result = await generate_report(state)
        report = result["final_report"]
        assert "reserved for later mvp" in report.lower()
        assert "spice" in report.lower()

    @pytest.mark.asyncio
    async def test_report_geant4_only_no_reservation(self, tmp_path: Path) -> None:
        state = {
            "job_id": "rpt-g4only",
            "user_query": "test",
            "task_spec": {
                "simulation_scope": ["geant4"],
                "particle": {"type": "proton"},
            },
            "rag_required_sources": ["geant4"],
            "rag_optional_sources": [],
            "rag_sufficiency_score": 0.95,
            "rag_sufficiency_report": {"decision": "allow_rag"},
            "proposed_patch": {},
            "gate_results": [],
            "simulation_results": {},
            "data_contract_results": {},
            "failure_report": {},
            "execution_mode": "dev_no_geant4_env",
            "skipped_gates": [],
            "context_decision": "allow_rag",
            "web_context": [],
        }
        with patch("agent_core.nodes.generate_report.get_job_dir", return_value=tmp_path):
            (tmp_path / "10_report").mkdir(parents=True, exist_ok=True)
            result = await generate_report(state)
        report = result["final_report"]
        # Geant4-only should NOT mention "reserved for later MVP"
        assert "reserved for later MVP" not in report.lower()
        assert "MVP-1 Scope" in report
        assert "Geant4 only" in report
