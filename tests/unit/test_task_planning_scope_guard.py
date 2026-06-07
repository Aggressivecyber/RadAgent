"""Tests for Task Planning Scope Guard — TCAD/SPICE must be blocked."""

from __future__ import annotations


from agent_core.graph.main_routes import route_after_task_planning


class TestTaskPlanningScopeGuard:
    """Verify TCAD/SPICE scopes are hard-blocked from G4 subgraphs."""

    def _make_state(self, scope: list[str], status: str = "completed") -> dict:
        return {
            "task_planning_status": status,
            "simulation_scope": scope,
        }

    def test_geant4_proceeds_to_modeling(self) -> None:
        """Pure geant4 scope must enter g4_modeling_subgraph."""
        state = self._make_state(["geant4"])
        assert route_after_task_planning(state) == "g4_modeling_subgraph"

    def test_tcad_blocked(self) -> None:
        """TCAD scope must be routed to report_subgraph."""
        state = self._make_state(["tcad"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_spice_blocked(self) -> None:
        """SPICE scope must be routed to report_subgraph."""
        state = self._make_state(["spice"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_geant4_plus_tcad_blocked(self) -> None:
        """Mixed geant4+tcad must be blocked — no partial G4 modeling."""
        state = self._make_state(["geant4", "tcad"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_full_chain_blocked(self) -> None:
        """full_chain scope must be blocked."""
        state = self._make_state(["full_chain"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_geant4_tcad_spice_blocked(self) -> None:
        """All three scopes together must be blocked."""
        state = self._make_state(["geant4", "tcad", "spice"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_geant4_to_tcad_blocked(self) -> None:
        """geant4_to_tcad bridge scope must be blocked."""
        state = self._make_state(["geant4_to_tcad"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_tcad_to_spice_blocked(self) -> None:
        """tcad_to_spice bridge scope must be blocked."""
        state = self._make_state(["tcad_to_spice"])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_failed_status_goes_to_report(self) -> None:
        """Failed planning always goes to report, regardless of scope."""
        state = self._make_state(["geant4"], status="failed")
        assert route_after_task_planning(state) == "report_subgraph"

    def test_empty_scope_goes_to_report(self) -> None:
        """Empty scope goes to report."""
        state = self._make_state([])
        assert route_after_task_planning(state) == "report_subgraph"

    def test_unknown_scope_goes_to_report(self) -> None:
        """Unknown scope string goes to report."""
        state = self._make_state(["unknown_scope"])
        assert route_after_task_planning(state) == "report_subgraph"
