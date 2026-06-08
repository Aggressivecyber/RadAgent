from __future__ import annotations

from pathlib import Path

import pytest

from tests.real_g4_modules.common import run_real_module_flow


async def test_real_main_cmake_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result, hard_gate, llm_gate = await run_real_module_flow(
        tmp_path, monkeypatch, "main_cmake", ("CMakeLists.txt", "main.cc")
    )
    paths = {f.path for f in result.generated_files}
    assert "CMakeLists.txt" in paths
    assert "main.cc" in paths
    assert hard_gate.status == "pass"
    assert llm_gate.status == "pass"
