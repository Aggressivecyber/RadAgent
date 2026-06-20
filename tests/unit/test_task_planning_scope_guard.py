"""Tests for Task Planning Scope Guard."""

from __future__ import annotations

from agent_core.graph.main_routes import route_after_task_planning
from agent_core.planning.nodes import detect_scope, validate_supported_scope


class TestTaskPlanningScopeGuard:
    """Verify task planning routes all supported requests to requirements review."""

    def _make_state(self, scope: list[str], status: str = "completed") -> dict:
        return {
            "task_planning_status": status,
            "simulation_scope": scope,
        }

    def test_geant4_proceeds_to_requirements_review(self) -> None:
        """Pure geant4 scope must enter pre-modeling requirements review."""
        state = self._make_state(["geant4"])
        assert route_after_task_planning(state) == "requirements_review"

    def test_non_empty_scope_words_proceed_to_requirements_review(self) -> None:
        state = self._make_state(["external_tool"])
        assert route_after_task_planning(state) == "requirements_review"

    def test_needs_user_input_proceeds_to_requirements_review(self) -> None:
        state = self._make_state(["geant4"], status="needs_user_input")
        assert route_after_task_planning(state) == "requirements_review"

    def test_failed_status_goes_to_report(self) -> None:
        """Failed planning always goes to report, regardless of scope."""
        state = self._make_state(["geant4"], status="failed")
        assert route_after_task_planning(state) == "report_subgraph"

    def test_empty_scope_defaults_to_requirements_review(self) -> None:
        state = self._make_state([])
        assert route_after_task_planning(state) == "requirements_review"

    def test_unknown_scope_defaults_to_requirements_review(self) -> None:
        state = self._make_state(["unknown_scope"])
        assert route_after_task_planning(state) == "requirements_review"

    def test_reserved_status_goes_to_report_for_legacy_snapshots(self) -> None:
        state = self._make_state(["geant4", "legacy_reserved"], status="reserved")
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

    def test_mosfet_g4_irradiation_is_geant4_scope(self) -> None:
        result = detect_scope("做一个mosfet的g4辐照仿真")
        assert result == ["geant4"]

    def test_device_simulation_words_return_geant4_scope(self) -> None:
        result = detect_scope("半导体器件仿真")
        assert result == ["geant4"]

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

    def test_external_scope_word_is_supported(self) -> None:
        result = validate_supported_scope(["external_tool"])
        assert result["task_planning_status"] == "passed"

    def test_unknown_scope_is_treated_as_geant4_context(self) -> None:
        result = validate_supported_scope(["unknown"])
        assert result["task_planning_status"] == "passed"
