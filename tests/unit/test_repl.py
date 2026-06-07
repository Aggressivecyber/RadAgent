"""Unit tests for agent_core.repl — RadAgentREPL."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.repl import (
    _AUTO_PHASES,
    _INTERACTIVE_PHASES,
    _PIPELINE_PHASES,
    _QuitREPL,
    RadAgentREPL,
)


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def repl() -> RadAgentREPL:
    """Create a RadAgentREPL instance with mocked console."""
    r = RadAgentREPL(execution_mode="dev_no_geant4_env")
    r.console = MagicMock()
    return r


@pytest.fixture
def repl_with_state(repl: RadAgentREPL, tmp_path: Path) -> RadAgentREPL:
    """Create a REPL with a basic pipeline state."""
    repl.state = {
        "job_id": "test-job-123",
        "user_query": "Test simulation",
        "execution_mode": "dev_no_geant4_env",
        "errors": [],
        "retry_count": 0,
        "max_retries_reached": False,
        "skipped_gates": [],
    }
    return repl


# ─── Pipeline phase constants ────────────────────────────────────────


class TestPipelineConstants:
    """Test pipeline phase constants are consistent."""

    def test_phases_ordered(self) -> None:
        assert _PIPELINE_PHASES[0] == "prepare_workspace"
        assert _PIPELINE_PHASES[-1] == "report"

    def test_auto_and_interactive_disjoint(self) -> None:
        assert _AUTO_PHASES.isdisjoint(_INTERACTIVE_PHASES)

    def test_all_phases_covered(self) -> None:
        all_phases = _AUTO_PHASES | _INTERACTIVE_PHASES
        for phase in _PIPELINE_PHASES:
            assert phase in all_phases, (
                f"Phase {phase} not in auto or interactive sets"
            )


# ─── REPL construction ───────────────────────────────────────────────


class TestRadAgentREPLInit:
    """Test REPL initialization."""

    def test_default_execution_mode(self) -> None:
        r = RadAgentREPL()
        assert r.execution_mode == "mvp1_acceptance"

    def test_custom_execution_mode(self) -> None:
        r = RadAgentREPL(execution_mode="dev_no_geant4_env")
        assert r.execution_mode == "dev_no_geant4_env"

    def test_initial_state_empty(self, repl: RadAgentREPL) -> None:
        assert repl.state == {}
        assert repl.current_phase_idx == 0
        assert repl._completed_phases == []

    def test_invalid_execution_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid execution_mode"):
            RadAgentREPL(execution_mode="invalid_mode")


# ─── Input dispatch ──────────────────────────────────────────────────


class TestHandleInput:
    """Test input dispatch logic."""

    @pytest.mark.asyncio
    async def test_slash_command_dispatched(self, repl: RadAgentREPL) -> None:
        """Slash commands should be dispatched to handlers."""
        with patch.object(repl, "_dispatch_command", new_callable=AsyncMock) as mock:
            await repl.handle_input("/status")
            mock.assert_called_once_with("/status", "")

    @pytest.mark.asyncio
    async def test_slash_command_with_arg(self, repl: RadAgentREPL) -> None:
        """Slash commands with arguments should split correctly."""
        with patch.object(repl, "_dispatch_command", new_callable=AsyncMock) as mock:
            await repl.handle_input("/run 1000")
            mock.assert_called_once_with("/run", "1000")

    @pytest.mark.asyncio
    async def test_natural_language_treated_as_run(self, repl: RadAgentREPL) -> None:
        """Natural language input should be treated as /run."""
        with patch.object(repl, "cmd_run", new_callable=AsyncMock) as mock:
            await repl.handle_input("simulate proton beam")
            mock.assert_called_once_with("simulate proton beam")

    @pytest.mark.asyncio
    async def test_empty_input_ignored(self, repl: RadAgentREPL) -> None:
        """Empty/whitespace input should be ignored."""
        with patch.object(repl, "_dispatch_command", new_callable=AsyncMock) as mock:
            await repl.handle_input("   ")
            mock.assert_not_called()


# ─── Slash command dispatch ──────────────────────────────────────────


class TestSlashCommands:
    """Test slash command routing."""

    @pytest.mark.asyncio
    async def test_unknown_command(self, repl: RadAgentREPL) -> None:
        """Unknown commands should print a warning."""
        await repl._dispatch_command("/unknown", "")
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_help_command(self, repl: RadAgentREPL) -> None:
        """Help command should display help panel."""
        await repl._dispatch_command("/help", "")
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_run_routes_to_cmd_run(self, repl: RadAgentREPL) -> None:
        """/run should route to cmd_run (pipeline), not cmd_run_sim."""
        with patch.object(repl, "cmd_run", new_callable=AsyncMock) as mock_run:
            await repl._dispatch_command("/run", "test query")
            mock_run.assert_called_once_with("test query")

    @pytest.mark.asyncio
    async def test_sim_routes_to_cmd_run_sim(self, repl: RadAgentREPL) -> None:
        """/sim should route to cmd_run_sim (Geant4 simulation)."""
        with patch.object(repl, "cmd_run_sim", new_callable=AsyncMock) as mock_sim:
            await repl._dispatch_command("/sim", "5000")
            mock_sim.assert_called_once_with("5000")

    @pytest.mark.asyncio
    async def test_quit_raises_quit_exception(self, repl: RadAgentREPL) -> None:
        """/quit should raise _QuitREPL, not SystemExit."""
        with pytest.raises(_QuitREPL):
            await repl._cmd_quit()

    @pytest.mark.asyncio
    async def test_status_no_pipeline(self, repl: RadAgentREPL) -> None:
        """Status with no pipeline should show a message."""
        await repl.cmd_status()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_step_no_pipeline(self, repl: RadAgentREPL) -> None:
        """Step with no pipeline should show a message."""
        await repl.cmd_step()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_model_no_ir(self, repl: RadAgentREPL) -> None:
        """Model with no IR should show a message."""
        await repl.cmd_model()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_code_no_dir(self, repl: RadAgentREPL) -> None:
        """Code with no generated code should show a message."""
        await repl.cmd_code()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_build_no_code(self, repl: RadAgentREPL) -> None:
        """Build with no generated code should show a message."""
        await repl.cmd_build()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_run_sim_no_exe(self, repl: RadAgentREPL) -> None:
        """Run sim with no executable should show a message."""
        await repl.cmd_run_sim("")
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_results_no_output(self, repl: RadAgentREPL) -> None:
        """Results with no simulation output should show a message."""
        await repl.cmd_results()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_gates_no_results(self, repl: RadAgentREPL) -> None:
        """Gates with no gate results should show a message."""
        await repl.cmd_gates()
        repl.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_jobs_no_dir(self, repl: RadAgentREPL, tmp_path: Path) -> None:
        """Jobs with no workspace dir should show a message."""
        with patch(
            "agent_core.workspace.manager.WorkspaceManager.root",
            new_callable=lambda: property(lambda self: tmp_path / "nonexistent"),
        ):
            r = RadAgentREPL()
            r.console = MagicMock()
            await r.cmd_jobs()
            r.console.print.assert_called()


# ─── cmd_status with pipeline state ──────────────────────────────────


class TestCmdStatus:
    """Test /status command with active pipeline."""

    @pytest.mark.asyncio
    async def test_status_with_state(self, repl_with_state: RadAgentREPL) -> None:
        """Status should display pipeline state."""
        repl_with_state._completed_phases = ["prepare_workspace", "context"]
        repl_with_state.current_phase_idx = 2
        await repl_with_state.cmd_status()
        repl_with_state.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_status_shows_key_fields(self, repl_with_state: RadAgentREPL) -> None:
        """Status should show key status fields."""
        repl_with_state.state["g4_modeling_status"] = "passed"
        repl_with_state.state["validation_status"] = "VERIFIED"
        await repl_with_state.cmd_status()
        repl_with_state.console.print.assert_called()


# ─── cmd_model ───────────────────────────────────────────────────────


class TestCmdModel:
    """Test /model command."""

    @pytest.mark.asyncio
    async def test_model_with_ir(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Model should display IR components."""
        ir_path = tmp_path / "g4_model_ir.json"
        ir_data = {
            "model_ir_id": "test",
            "modeling_mode": "realistic",
            "components": [
                {
                    "component_id": "water",
                    "component_type": "volume",
                    "material_id": "G4_WATER",
                    "roles": ["target"],
                }
            ],
            "sources": [
                {"source_id": "beam", "particle_type": "proton", "energy": "100 MeV"}
            ],
            "scoring": [
                {"scoring_id": "dose", "scoring_type": "dose", "volume": "water"}
            ],
        }
        ir_path.write_text(json.dumps(ir_data), encoding="utf-8")
        repl_with_state.state["g4_model_ir_path"] = str(ir_path)

        await repl_with_state.cmd_model()
        repl_with_state.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_model_corrupted_json(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Model with corrupted JSON should show error message."""
        ir_path = tmp_path / "g4_model_ir.json"
        ir_path.write_text("{bad json", encoding="utf-8")
        repl_with_state.state["g4_model_ir_path"] = str(ir_path)

        await repl_with_state.cmd_model()
        repl_with_state.console.print.assert_called()


# ─── cmd_gates ───────────────────────────────────────────────────────


class TestCmdGates:
    """Test /gates command."""

    @pytest.mark.asyncio
    async def test_gates_with_results(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Gates should display results table."""
        gates_path = tmp_path / "gate_results.json"
        gates_data = {
            "results": [
                {
                    "gate_id": "0",
                    "name": "Context Sufficiency",
                    "status": "pass",
                    "message": "All checks passed",
                },
                {
                    "gate_id": "5",
                    "name": "Static Check",
                    "status": "fail",
                    "message": "Missing include guard",
                },
            ]
        }
        gates_path.write_text(json.dumps(gates_data), encoding="utf-8")
        repl_with_state.state["gate_results_path"] = str(gates_path)

        await repl_with_state.cmd_gates()
        repl_with_state.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_gates_corrupted_json(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Gates with corrupted JSON should show error."""
        gates_path = tmp_path / "gate_results.json"
        gates_path.write_text("{broken", encoding="utf-8")
        repl_with_state.state["gate_results_path"] = str(gates_path)

        await repl_with_state.cmd_gates()
        repl_with_state.console.print.assert_called()


# ─── cmd_run_sim ─────────────────────────────────────────────────────


class TestCmdRunSim:
    """Test /sim simulation command."""

    @pytest.mark.asyncio
    async def test_run_sim_with_exe(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Run sim should call Geant4Runner.simulate."""
        exe_path = tmp_path / "my_sim"
        exe_path.touch()
        exe_path.chmod(0o755)
        repl_with_state.state["_executable_path"] = str(exe_path)

        mock_result = {
            "success": True,
            "output_dir": "/tmp/out",
            "log": "",
            "errors": "",
        }
        with patch(
            "agent_core.tools.geant4_runner.Geant4Runner.simulate",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await repl_with_state.cmd_run_sim("2000")
            repl_with_state.console.print.assert_called()

    @pytest.mark.asyncio
    async def test_run_sim_default_events(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Run sim without events arg should default to 1000."""
        exe_path = tmp_path / "my_sim"
        exe_path.touch()
        exe_path.chmod(0o755)
        repl_with_state.state["_executable_path"] = str(exe_path)

        mock_result = {
            "success": True,
            "output_dir": "/tmp/out",
            "log": "",
            "errors": "",
        }
        with patch(
            "agent_core.tools.geant4_runner.Geant4Runner.simulate",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_sim:
            await repl_with_state.cmd_run_sim("")
            call_kwargs = mock_sim.call_args[1]
            assert call_kwargs["events"] == 1000

    @pytest.mark.asyncio
    async def test_run_sim_invalid_events_defaults_with_warning(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Invalid event count should default to 1000 with a warning."""
        exe_path = tmp_path / "my_sim"
        exe_path.touch()
        exe_path.chmod(0o755)
        repl_with_state.state["_executable_path"] = str(exe_path)

        mock_result = {
            "success": True,
            "output_dir": "/tmp/out",
            "log": "",
            "errors": "",
        }
        with patch(
            "agent_core.tools.geant4_runner.Geant4Runner.simulate",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_sim:
            await repl_with_state.cmd_run_sim("abc")
            call_kwargs = mock_sim.call_args[1]
            assert call_kwargs["events"] == 1000
            # Should have printed a warning about invalid count
            repl_with_state.console.print.assert_called()


# ─── cmd_code ────────────────────────────────────────────────────────


class TestCmdCode:
    """Test /code command."""

    @pytest.mark.asyncio
    async def test_code_lists_files(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Code should list generated C++ files."""
        code_dir = tmp_path / "generated"
        code_dir.mkdir()
        (code_dir / "DetectorConstruction.cc").write_text(
            "// detector\nline2\nline3\n"
        )
        (code_dir / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.16)\n"
        )

        repl_with_state.state["generated_code_dir"] = str(code_dir)

        with patch.object(repl_with_state, "_prompt_text", return_value=""):
            await repl_with_state.cmd_code()
            repl_with_state.console.print.assert_called()


# ─── cmd_confirm ─────────────────────────────────────────────────────


class TestCmdConfirm:
    """Test /confirm command."""

    @pytest.mark.asyncio
    async def test_confirm_auto_approve_no_questions(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Confirm with no questions should auto-approve."""
        request_path = tmp_path / "confirmation_request.json"
        request_data = {"round_id": 1, "questions": []}
        request_path.write_text(json.dumps(request_data), encoding="utf-8")
        repl_with_state.state["confirmation_request_path"] = str(request_path)

        await repl_with_state.cmd_confirm()

        response = repl_with_state.state["raw_human_response"]
        assert response["user_decision"] == "approve"

    @pytest.mark.asyncio
    async def test_confirm_interactive_qa(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Confirm with questions should prompt user."""
        request_path = tmp_path / "confirmation_request.json"
        request_data = {
            "round_id": 1,
            "questions": [
                {
                    "field_path": "sources.primary.energy",
                    "current_value": "150 MeV",
                    "reason": "Standard energy",
                    "confidence": 0.8,
                },
            ],
        }
        request_path.write_text(json.dumps(request_data), encoding="utf-8")
        repl_with_state.state["confirmation_request_path"] = str(request_path)

        with patch.object(repl_with_state, "_prompt_choice", return_value="a"):
            await repl_with_state.cmd_confirm()

        response = repl_with_state.state["raw_human_response"]
        assert response["user_decision"] == "approve"

    @pytest.mark.asyncio
    async def test_confirm_with_edit(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Confirm with edits should record edits."""
        request_path = tmp_path / "confirmation_request.json"
        request_data = {
            "round_id": 1,
            "questions": [
                {
                    "field_path": "sources.primary.energy",
                    "current_value": "150 MeV",
                    "reason": "Standard",
                    "confidence": 0.8,
                },
            ],
        }
        request_path.write_text(json.dumps(request_data), encoding="utf-8")
        repl_with_state.state["confirmation_request_path"] = str(request_path)

        with (
            patch.object(repl_with_state, "_prompt_choice", return_value="e"),
            patch.object(repl_with_state, "_prompt_text", return_value="200 MeV"),
        ):
            await repl_with_state.cmd_confirm()

        response = repl_with_state.state["raw_human_response"]
        assert response["user_decision"] == "edit"
        assert len(response["edits"]) == 1
        assert response["edits"][0]["new_value"] == "200 MeV"

    @pytest.mark.asyncio
    async def test_confirm_with_reject(
        self, repl_with_state: RadAgentREPL, tmp_path: Path
    ) -> None:
        """Confirm with rejection should record reject decision."""
        request_path = tmp_path / "confirmation_request.json"
        request_data = {
            "round_id": 1,
            "questions": [
                {
                    "field_path": "components.shield.thickness",
                    "current_value": "2mm",
                    "reason": "Assumed",
                    "confidence": 0.6,
                },
            ],
        }
        request_path.write_text(json.dumps(request_data), encoding="utf-8")
        repl_with_state.state["confirmation_request_path"] = str(request_path)

        with patch.object(repl_with_state, "_prompt_choice", return_value="r"):
            await repl_with_state.cmd_confirm()

        response = repl_with_state.state["raw_human_response"]
        assert response["user_decision"] == "edit"
        assert len(response["edits"]) == 1
        assert response["edits"][0]["new_value"] is None


# ─── build_subgraph_nodes integration ────────────────────────────────


class TestBuildSubgraphNodes:
    """Test that build_subgraph_nodes returns valid functions."""

    def test_returns_all_phases(self) -> None:
        """Should return a function for each subgraph phase."""
        from agent_core.graph.main_graph import build_subgraph_nodes

        nodes = build_subgraph_nodes()
        expected = {
            "context", "task_planning", "g4_modeling",
            "human_confirmation", "g4_codegen", "patch",
            "gate", "artifact", "report",
        }
        assert set(nodes.keys()) == expected

    def test_all_nodes_are_callable(self) -> None:
        """Each node should be a callable."""
        from agent_core.graph.main_graph import build_subgraph_nodes

        nodes = build_subgraph_nodes()
        for name, fn in nodes.items():
            assert callable(fn), f"{name} is not callable"


# ─── _render_model_summary ───────────────────────────────────────────


class TestRenderModelSummary:
    """Test model IR rendering."""

    def test_renders_components_table(self, repl: RadAgentREPL) -> None:
        """Should render a components table."""
        model_ir = {
            "model_ir_id": "test",
            "modeling_mode": "realistic",
            "components": [
                {
                    "component_id": "detector",
                    "component_type": "volume",
                    "material_id": "G4_SILICON",
                    "roles": ["target"],
                }
            ],
            "sources": [],
            "scoring": [],
        }
        repl._render_model_summary(model_ir)
        repl.console.print.assert_called()

    def test_renders_empty_model(self, repl: RadAgentREPL) -> None:
        """Should handle empty model IR gracefully."""
        model_ir = {"model_ir_id": "empty"}
        repl._render_model_summary(model_ir)
        repl.console.print.assert_called()


# ─── _load_json_safe ─────────────────────────────────────────────────


class TestLoadJsonSafe:
    """Test _load_json_safe utility."""

    def test_loads_valid_json(self, tmp_path: Path) -> None:
        from agent_core.repl import _load_json_safe

        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        result = _load_json_safe(p)
        assert result == {"key": "value"}

    def test_returns_none_for_corrupted(self, tmp_path: Path) -> None:
        from agent_core.repl import _load_json_safe

        p = tmp_path / "bad.json"
        p.write_text("{broken", encoding="utf-8")
        result = _load_json_safe(p)
        assert result is None
