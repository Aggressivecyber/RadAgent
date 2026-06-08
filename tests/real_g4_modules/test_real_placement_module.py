from __future__ import annotations

from pathlib import Path

import pytest

from tests.real_g4_modules.common import run_real_module_flow


async def test_real_placement_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, hard_gate, llm_gate = await run_real_module_flow(
        tmp_path, monkeypatch, "placement", ("PlacementManager",)
    )
    assert result.generated_files
    assert hard_gate.status == "pass"
    assert llm_gate.status == "pass"
