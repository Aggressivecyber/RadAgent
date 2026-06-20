from __future__ import annotations

import json
from pathlib import Path

from agent_core.observability import clear_failure_bundle, record_event, write_failure_bundle
from agent_core.observability.redaction import sanitize


def test_observability_event_writes_job_logs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

    event = record_event(
        job_id="obs_job",
        event_type="model_call",
        status="failed",
        phase="g4_codegen",
        module_name="material",
        summary="model failed",
        errors=["connection failed"],
        details={"api_key": "secret-value", "url": "https://example.test?api_key=abc"},
    )

    assert event is not None
    log_dir = tmp_path / "jobs" / "obs_job" / "logs"
    events = log_dir / "events.jsonl"
    trace = log_dir / "trace.json"
    assert events.exists()
    assert trace.exists()

    payload = json.loads(events.read_text().splitlines()[0])
    assert payload["event_type"] == "model_call"
    assert payload["details"]["api_key"] == "<redacted>"
    assert payload["details"]["url"] == "https://example.test?api_key=<redacted>"


def test_failure_bundle_includes_recent_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    record_event(
        job_id="bundle_job",
        event_type="module_gate_result",
        status="failed",
        phase="g4_codegen",
        errors=["hard gate failed"],
    )

    path = write_failure_bundle(
        job_id="bundle_job",
        status="failed",
        phase="g4_codegen",
        errors=["hard gate failed"],
    )

    assert path is not None
    bundle = json.loads(path.read_text())
    assert bundle["status"] == "failed"
    assert bundle["recent_events"]


def test_clear_failure_bundle_removes_stale_failure_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    path = write_failure_bundle(
        job_id="bundle_job",
        status="failed",
        phase="gate_validation",
        errors=["old gate failure"],
    )
    assert path is not None
    assert path.is_file()

    assert clear_failure_bundle(job_id="bundle_job") is True

    assert not path.exists()


def test_sanitize_truncates_large_strings() -> None:
    sanitized = sanitize({"content": "x" * 2000}, max_string=20)
    assert sanitized["content"]["truncated"] is True
    assert sanitized["content"]["byte_count"] == 2000
