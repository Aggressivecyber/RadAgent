"""Tests for Task Planning Scope Guard — TCAD/SPICE must be blocked."""

from __future__ import annotations

from agent_core.graph.main_routes import route_after_task_planning
from agent_core.planning.nodes import detect_scope, validate_supported_scope


class TestTaskPlanningScopeGuard:
    """Verify TCAD/SPICE scopes are hard-blocked from G4 subgraphs."""

    def _make_state(self, scope: list[str], status: str = "completed") -> dict:
        return {
            "task_planning_status": status,
            "simulation_scope": scope,
        }

    def test_geant4_proceeds_to_requirements_review(self) -> None:
        """Pure geant4 scope must enter pre-modeling requirements review."""
        state = self._make_state(["geant4"])
        assert route_after_task_planning(state) == "requirements_review"

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

    def test_reserved_status_goes_to_report(self) -> None:
        """Reserved status (TCAD/SPICE detected) goes to report."""
        state = self._make_state(["geant4", "tcad"], status="reserved")
        assert route_after_task_planning(state) == "report_subgraph"


class TestDetectScope:
    """Test detect_scope keyword matching."""

    def test_geant4_english_keyword(self) -> None:
        assert "geant4" in detect_scope("Run geant4 simulation")

    def test_geant4_g4_keyword(self) -> None:
        assert "geant4" in detect_scope("G4 particle transport")

    def test_geant4_chinese_keyword(self) -> None:
        assert "geant4" in detect_scope("蒙特卡罗粒子输运仿真")

    def test_geant4_dose_keyword(self) -> None:
        assert "geant4" in detect_scope("剂量分布计算")

    def test_tcad_english_keyword(self) -> None:
        result = detect_scope("TCAD device simulation with sentaurus")
        assert "tcad" in result

    def test_tcad_chinese_keyword(self) -> None:
        result = detect_scope("半导体器件仿真")
        assert "tcad" in result

    def test_spice_english_keyword(self) -> None:
        result = detect_scope("ngspice circuit simulation")
        assert "spice" in result

    def test_spice_chinese_keyword(self) -> None:
        result = detect_scope("电路仿真网表")
        assert "spice" in result

    def test_full_chain_chinese_keyword(self) -> None:
        result = detect_scope("联合仿真全链路")
        assert "full_chain" in result

    def test_default_geant4_when_no_keywords(self) -> None:
        result = detect_scope("模拟探测器响应")
        assert result == ["geant4"]

    def test_deduplication(self) -> None:
        """Repeated keywords should not produce duplicates."""
        result = detect_scope("geant4 geant4 geant4")
        assert result.count("geant4") == 1


class TestValidateSupportedScope:
    """Test validate_supported_scope returns correct status."""

    def test_pure_geant4_passes(self) -> None:
        result = validate_supported_scope(["geant4"])
        assert result["task_planning_status"] == "passed"
        assert result["reserved_scopes"] == []

    def test_tcad_is_reserved(self) -> None:
        result = validate_supported_scope(["tcad"])
        assert result["task_planning_status"] == "reserved"
        assert "tcad" in result["reserved_scopes"]

    def test_spice_is_reserved(self) -> None:
        result = validate_supported_scope(["spice"])
        assert result["task_planning_status"] == "reserved"
        assert "spice" in result["reserved_scopes"]

    def test_geant4_tcad_is_reserved(self) -> None:
        result = validate_supported_scope(["geant4", "tcad"])
        assert result["task_planning_status"] == "reserved"

    def test_full_chain_is_reserved(self) -> None:
        result = validate_supported_scope(["full_chain"])
        assert result["task_planning_status"] == "reserved"

    def test_unknown_scope_fails(self) -> None:
        result = validate_supported_scope(["unknown"])
        assert result["task_planning_status"] == "failed"
