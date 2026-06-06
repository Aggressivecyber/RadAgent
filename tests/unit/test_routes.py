"""Tests for graph routing functions — route targets and MVP-1 skip rejection."""

from __future__ import annotations

from agent_core.graph.routes import (
    route_after_classify_failure,
    route_after_combined_context,
    route_after_gate_checks,
    route_after_rag,
    route_after_sim_ir_validation,
    route_after_task_spec_validation,
)


class TestRouteAfterRAG:
    """route_after_rag: RAG decision → next node."""

    def test_allow_rag_to_plan(self) -> None:
        state = {"context_decision": "allow_rag"}
        assert route_after_rag(state) == "plan_simulation"

    def test_needs_web_to_retrieve(self) -> None:
        state = {"context_decision": "needs_web"}
        assert route_after_rag(state) == "retrieve_web_context"

    def test_block_no_context_to_report(self) -> None:
        state = {"context_decision": "block_no_context"}
        assert route_after_rag(state) == "generate_report"

    def test_default_is_terminate(self) -> None:
        """Unknown/missing decision defaults to generate_report."""
        assert route_after_rag({}) == "generate_report"
        assert route_after_rag({"context_decision": "unknown"}) == "generate_report"


class TestRouteAfterCombinedContext:
    """route_after_combined_context: combined decision → next node."""

    def test_allow_rag_to_plan(self) -> None:
        state = {"context_decision": "allow_rag"}
        assert route_after_combined_context(state) == "plan_simulation"

    def test_allow_with_web_to_plan(self) -> None:
        state = {"context_decision": "allow_with_web_supplement"}
        assert route_after_combined_context(state) == "plan_simulation"

    def test_block_no_context_to_report(self) -> None:
        state = {"context_decision": "block_no_context"}
        assert route_after_combined_context(state) == "generate_report"

    def test_default_is_terminate(self) -> None:
        assert route_after_combined_context({}) == "generate_report"


class TestRouteAfterGateChecks:
    """route_after_gate_checks: gate severity + execution mode routing."""

    def test_all_pass_to_parse(self) -> None:
        state = {
            "gate_results": [
                {"gate_id": i, "passed": True, "severity": "pass"}
                for i in range(12)
            ],
            "execution_mode": "dev_no_geant4_env",
        }
        assert route_after_gate_checks(state) == "parse_simulation_results"

    def test_hard_failure_to_classify(self) -> None:
        state = {
            "gate_results": [
                {"gate_id": 0, "passed": True, "severity": "pass"},
                {"gate_id": 1, "passed": False, "severity": "fail"},
            ],
            "execution_mode": "dev_no_geant4_env",
        }
        assert route_after_gate_checks(state) == "classify_failure"

    def test_block_severity_to_classify(self) -> None:
        state = {
            "gate_results": [
                {"gate_id": 0, "passed": False, "severity": "block"},
            ],
            "execution_mode": "dev_no_geant4_env",
        }
        assert route_after_gate_checks(state) == "classify_failure"

    def test_dev_mode_skip_allowed(self) -> None:
        """Dev mode: skipped critical gate → proceed to parse."""
        state = {
            "gate_results": [
                {"gate_id": 6, "passed": False, "severity": "skipped"},
            ],
            "execution_mode": "dev_no_geant4_env",
        }
        assert route_after_gate_checks(state) == "parse_simulation_results"

    def test_mvp1_critical_skip_rejected(self) -> None:
        """MVP-1 mode: skipped critical gate (6/8/9/11) → classify_failure."""
        for gate_id in (6, 8, 9, 11):
            state = {
                "gate_results": [
                    {"gate_id": gate_id, "passed": False, "severity": "skipped"},
                ],
                "execution_mode": "mvp1_acceptance",
            }
            assert route_after_gate_checks(state) == "classify_failure", (
                f"Gate {gate_id} skip should be rejected in MVP-1"
            )

    def test_mvp1_non_critical_skip_ok(self) -> None:
        """MVP-1 mode: skipped non-critical gate → proceed."""
        state = {
            "gate_results": [
                {"gate_id": 7, "passed": True, "severity": "skipped"},
            ],
            "execution_mode": "mvp1_acceptance",
        }
        assert route_after_gate_checks(state) == "parse_simulation_results"

    def test_warning_gates_proceed(self) -> None:
        """Warning severity gates should proceed."""
        state = {
            "gate_results": [
                {"gate_id": 0, "passed": True, "severity": "warning"},
            ],
            "execution_mode": "mvp1_acceptance",
        }
        assert route_after_gate_checks(state) == "parse_simulation_results"


class TestRouteAfterTaskSpecValidation:
    """route_after_task_spec_validation: retry vs terminate."""

    def test_valid_proceeds(self) -> None:
        state = {"task_spec_errors": [], "retry_count": 0}
        assert route_after_task_spec_validation(state) == "build_simulation_ir"

    def test_errors_below_max_retries(self) -> None:
        state = {"task_spec_errors": ["bad"], "retry_count": 1}
        assert route_after_task_spec_validation(state) == "build_task_spec"

    def test_errors_at_max_retries_terminates(self) -> None:
        state = {"task_spec_errors": ["bad"], "retry_count": 3}
        assert route_after_task_spec_validation(state) == "generate_report"

    def test_errors_above_max_retries_terminates(self) -> None:
        state = {"task_spec_errors": ["bad"], "retry_count": 5}
        assert route_after_task_spec_validation(state) == "generate_report"


class TestRouteAfterSimIRValidation:
    """route_after_sim_ir_validation: retry vs terminate."""

    def test_valid_proceeds(self) -> None:
        state = {"simulation_ir_errors": [], "retry_count": 0}
        assert route_after_sim_ir_validation(state) == "route_rag"

    def test_errors_below_max_retries(self) -> None:
        state = {"simulation_ir_errors": ["bad"], "retry_count": 2}
        assert route_after_sim_ir_validation(state) == "build_simulation_ir"

    def test_errors_at_max_retries_terminates(self) -> None:
        state = {"simulation_ir_errors": ["bad"], "retry_count": 3}
        assert route_after_sim_ir_validation(state) == "generate_report"


class TestRouteAfterClassifyFailure:
    """route_after_classify_failure: failure type routing."""

    def test_max_retries_terminates(self) -> None:
        state = {"retry_count": 5, "failure_report": {"type": "build_error"}}
        assert route_after_classify_failure(state) == "generate_report"

    def test_rag_insufficient_terminates(self) -> None:
        state = {"retry_count": 0, "failure_report": {"type": "rag_insufficient"}}
        assert route_after_classify_failure(state) == "generate_report"

    def test_schema_invalid_gets_error_context(self) -> None:
        state = {"retry_count": 0, "failure_report": {"type": "schema_invalid"}}
        assert route_after_classify_failure(state) == "retrieve_error_context"

    def test_build_error_gets_fix_patch(self) -> None:
        state = {"retry_count": 0, "failure_report": {"type": "build_error"}}
        assert route_after_classify_failure(state) == "write_fix_patch"

    def test_runtime_error_gets_fix_patch(self) -> None:
        state = {"retry_count": 0, "failure_report": {"type": "runtime_error"}}
        assert route_after_classify_failure(state) == "write_fix_patch"

    def test_permission_violation_terminates(self) -> None:
        state = {"retry_count": 0, "failure_report": {"type": "permission_violation"}}
        assert route_after_classify_failure(state) == "generate_report"

    def test_unknown_type_gets_error_context(self) -> None:
        state = {"retry_count": 0, "failure_report": {"type": "something_new"}}
        assert route_after_classify_failure(state) == "retrieve_error_context"
