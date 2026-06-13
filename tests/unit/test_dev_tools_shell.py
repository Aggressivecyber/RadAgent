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


def test_known_fix_hints_append_for_classic_geant4_errors() -> None:
    """The repair agent should see the deterministic fix, not just the raw error."""
    from agent_core.dev_tools.shell import _known_fix_hints

    particle = _known_fix_hints(
        "*** G4Exception : BeamPhys001\nParticle 'electron' not found in particle table."
    )
    assert "PARTICLE-TABLE FIX" in particle
    assert "ElectronDefinition" in particle

    overlap = _known_fix_hints("*** G4Exception : Geom0003\nVolume overlap detected")
    assert "OVERLAP FIX" in overlap
    assert "HALF-lengths" in overlap

    region = _known_fix_hints(
        "*** G4Exception : GeomMgt0002\nalready set as root for region <r>"
    )
    assert "REGION FIX" in region

    # Unrelated output passes through unchanged; empty stays empty.
    assert _known_fix_hints("undefined reference to foo") == "undefined reference to foo"
    assert _known_fix_hints("") == ""


def test_known_fix_hint_for_null_material() -> None:
    from agent_core.dev_tools.shell import _known_fix_hints
    out = _known_fix_hints(
        "*** G4Exception : GeomMgt0002\nNo material associated to the logical volume: X! GetMass"
    )
    assert "MATERIAL FIX" in out
    assert "G4_POLYSTYRENE" in out
