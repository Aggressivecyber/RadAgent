"""Tests for codegen dev shell tools used by agentic repair."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_run_smoke_requires_output_contract_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Process success alone must not stop repair before artifacts are valid."""
    from agent_core.dev_tools import shell

    class FakeRunner:
        async def smoke_test(
            self,
            project_dir: str,
            *,
            job_id: str = "unknown",
            output_dir: str | None = None,
            events: int = 10,
        ) -> dict[str, Any]:
            assert output_dir is not None
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "output_dir": output_dir,
                "warnings": [],
                "events_requested": events,
                "build_success": True,
                "run_success": True,
                "errors": "",
            }

    monkeypatch.setattr(
        "agent_core.tools.geant4_runner.Geant4Runner",
        lambda: FakeRunner(),
    )

    result = await shell.run_smoke(tmp_path, events=5, job_id="job_contract")

    assert result["ok"] is False
    assert result["stage"] == "smoke"
    assert "Missing output contract files" in result["output"]
    assert result["details"]["output_quality"]["status"] == "fail"
