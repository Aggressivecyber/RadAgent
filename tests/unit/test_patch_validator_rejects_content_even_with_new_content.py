"""P0-9: PatchValidator rejects content field even when new_content is also present."""

from __future__ import annotations

from agent_core.validators.patch_validator import PatchValidator


def _patch(*files: dict) -> dict:
    return {
        "patch_id": "test",
        "job_id": "test",
        "description": "test",
        "change_type": "create_or_replace",
        "risk_level": "low",
        "changed_files": list(files),
        "test_plan": ["test"],
        "expected_outputs": ["test"],
    }


def test_only_content_rejected():
    pv = PatchValidator()
    p = _patch({"path": "x.hh", "content": "data", "zone": "green"})
    ok, errs = pv.validate_patch_format(p)
    assert not ok
    assert any("content" in e for e in errs)


def test_content_with_new_content_rejected():
    pv = PatchValidator()
    p = _patch({"path": "x.hh", "content": "old", "new_content": "new", "zone": "green"})
    ok, errs = pv.validate_patch_format(p)
    assert not ok
    assert any("content" in e for e in errs)


def test_only_new_content_passes():
    pv = PatchValidator()
    p = _patch({"path": "x.hh", "new_content": "data", "zone": "green"})
    ok, errs = pv.validate_patch_format(p)
    assert ok, f"Unexpected errors: {errs}"
