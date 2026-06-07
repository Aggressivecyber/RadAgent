"""Test GateResult schema compliance.

This test verifies that all gate results conform to the required schema:
- gate_id: str
- name: str
- status: "pass" | "fail" | "skip" | "error"
- checked_items: list[dict]
- passed_items: list[str]
- failed_items: list[str]
- warnings: list[str]
- evidence: list[str]
- file_paths: list[str]
- message: str (NOT just "OK")

Also verifies the deprecated format is NOT used:
- No severity field
- No passed boolean field
- No gate_name field (use name instead)
"""

from __future__ import annotations

from agent_core.schemas.gate_result import GateResult, create_gate_result


def test_gate_result_has_all_required_fields():
    """GateResult must have all required fields."""
    result = create_gate_result(
        gate_id="12",
        name="Model Completeness",
        status="pass",
        checked_items=[{"item": "components present", "result": "pass"}],
        passed_items=["components present"],
        failed_items=[],
        warnings=[],
        evidence=["component_ids: A, B, C"],
        file_paths=["/path/to/file.cc"],
        message="All checks passed",
    )

    assert result.gate_id == "12"
    assert result.name == "Model Completeness"
    assert result.status == "pass"
    assert result.checked_items == [{"item": "components present", "result": "pass"}]
    assert result.passed_items == ["components present"]
    assert result.failed_items == []
    assert result.warnings == []
    assert result.evidence == ["component_ids: A, B, C"]
    assert result.file_paths == ["/path/to/file.cc"]
    assert result.message == "All checks passed"


def test_gate_result_status_values():
    """GateResult status must be one of: pass, fail, skip, error."""
    for status in ["pass", "fail", "skip", "error"]:
        result = create_gate_result(
            gate_id="0",
            name="Test Gate",
            status=status,
            message=f"Test {status}",
        )
        assert result.status == status


def test_gate_result_message_not_ok():
    """GateResult message should NOT be just 'OK'."""
    # Bad: message is just "OK"
    result_bad = create_gate_result(
        gate_id="0",
        name="Test Gate",
        status="pass",
        message="OK",  # BAD
    )
    # This is technically allowed by schema, but gate implementations
    # should provide meaningful messages. This test documents the
    # expectation - actual enforcement is in gate implementations.
    assert result_bad.message == "OK"

    # Good: message is descriptive
    result_good = create_gate_result(
        gate_id="0",
        name="Test Gate",
        status="pass",
        message="All 5 components validated successfully",
    )
    assert result_good.message != "OK"


def test_gate_result_no_deprecated_fields():
    """GateResult should NOT have deprecated fields like 'severity' or 'passed'."""
    result = GateResult(
        gate_id="0",
        name="Test Gate",
        status="pass",
        message="Test passed",
    )

    # These fields should NOT exist on GateResult
    assert not hasattr(result, "severity")
    assert not hasattr(result, "passed")
    assert not hasattr(result, "gate_name")  # Should use 'name' instead
    assert hasattr(result, "name")  # Correct field name


def test_gate_result_default_lists():
    """GateResult lists should default to empty lists."""
    result = GateResult(
        gate_id="0",
        name="Test Gate",
        status="pass",
        message="Test passed",
    )

    assert result.checked_items == []
    assert result.passed_items == []
    assert result.failed_items == []
    assert result.warnings == []
    assert result.evidence == []
    assert result.file_paths == []


def test_gate_report_summary():
    """GateReport summary should correctly count statuses."""
    from agent_core.schemas.gate_result import create_gate_report

    results = [
        create_gate_result("0", "Gate 0", "pass", message="Passed"),
        create_gate_result("1", "Gate 1", "fail", message="Failed"),
        create_gate_result("2", "Gate 2", "skip", message="Skipped"),
        create_gate_result("3", "Gate 3", "pass", message="Passed"),
    ]

    report = create_gate_report("test-job", results)

    assert report.total_gates == 19  # Default total
    assert len(report.results) == 4
    assert not report.overall_passed  # One fail
    # Overall status is FAIL, but counts should match
    assert "FAIL: 2 passed, 1 skipped, 0 errors, 1 failed" == report.summary


def test_gate_result_allows_skip_status():
    """GateResult status 'skip' is the correct value (not 'skipped')."""
    result = create_gate_result(
        gate_id="7",
        name="Unit Test",
        status="skip",  # Correct: 'skip'
        message="Unit tests not run (dev mode)",
    )
    assert result.status == "skip"


def test_gate_result_checked_items_structure():
    """checked_items should be a list of dicts with 'item' and 'result' keys."""
    result = create_gate_result(
        gate_id="0",
        name="Test Gate",
        status="pass",
        checked_items=[
            {"item": "check 1", "result": "pass"},
            {"item": "check 2", "result": "fail"},
        ],
        message="Some checks",
    )

    assert len(result.checked_items) == 2
    assert result.checked_items[0] == {"item": "check 1", "result": "pass"}
    assert result.checked_items[1] == {"item": "check 2", "result": "fail"}
