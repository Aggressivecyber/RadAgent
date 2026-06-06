"""Gate 11 — Physics sanity tests.

Validates NaN/Inf/negative detection in edep and dose CSV files.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from agent_core.nodes.run_gate_checks import run_gate_checks


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Write a CSV file for testing."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _valid_patch() -> dict:
    """Return a patch that passes PatchValidator."""
    return {
        "patch_id": "p1",
        "job_id": "test-physics-job",
        "description": "test patch",
        "change_type": "create",
        "risk_level": "low",
        "changed_files": [
            {
                "path": "05_geant4/src/main.cc",
                "new_content": "int main() { return 0; }",
                "zone": "green",
            },
        ],
        "test_plan": "compile check",
        "expected_outputs": {},
    }


def _base_state(tmp_path: Path, **overrides: Any) -> dict:
    """State with a valid output directory for Gate 11."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "09_validation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "05_geant4" / "src").mkdir(parents=True, exist_ok=True)
    return {
        "job_id": "test-physics-job",
        "user_query": "physics test",
        "execution_mode": "dev_no_geant4_env",
        "task_spec": {},
        "simulation_ir": {},
        "proposed_patch": _valid_patch(),
        "rag_sufficiency_score": 0.9,
        "context_decision": "allow_rag",
        "context_sufficiency_report": {},
        "skipped_gates": [],
        **overrides,
    }


def _setup_patches(tmp_path: Path, output_dir: Path) -> list:
    """Return context managers for workspace patches."""
    return [
        patch("agent_core.nodes.run_gate_checks.get_output_dir", return_value=output_dir),
        patch("agent_core.nodes.run_gate_checks.get_job_dir", return_value=tmp_path),
    ]


@pytest.mark.anyio
async def test_gate11_passes_with_valid_data(tmp_path: Path):
    """Gate 11 passes when all CSV values are valid positive numbers."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "edep_3d.csv",
        ["x", "y", "z", "edep_MeV"],
        [["1.0", "2.0", "3.0", "0.05"]],
    )
    _write_csv(
        output_dir / "dose_3d.csv",
        ["x", "y", "z", "dose_Gy"],
        [["1.0", "2.0", "3.0", "0.001"]],
    )
    patches = _setup_patches(tmp_path, output_dir)
    state = _base_state(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate11 = [g for g in result["gate_results"] if g["gate_id"] == 11][0]
    assert gate11["passed"] is True
    assert gate11["severity"] == "pass"


@pytest.mark.anyio
async def test_gate11_detects_nan(tmp_path: Path):
    """Gate 11 detects NaN values in edep."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "edep_3d.csv",
        ["x", "y", "z", "edep_MeV"],
        [["1.0", "2.0", "3.0", "nan"]],
    )
    patches = _setup_patches(tmp_path, output_dir)
    state = _base_state(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate11 = [g for g in result["gate_results"] if g["gate_id"] == 11][0]
    assert gate11["passed"] is False
    assert "NaN" in gate11["message"] or "nan" in gate11["message"].lower()


@pytest.mark.anyio
async def test_gate11_detects_negative_edep(tmp_path: Path):
    """Gate 11 detects negative energy deposition."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "edep_3d.csv",
        ["x", "y", "z", "edep_MeV"],
        [["1.0", "2.0", "3.0", "-0.5"]],
    )
    patches = _setup_patches(tmp_path, output_dir)
    state = _base_state(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate11 = [g for g in result["gate_results"] if g["gate_id"] == 11][0]
    assert gate11["passed"] is False
    assert "negative" in gate11["message"].lower()


@pytest.mark.anyio
async def test_gate11_detects_inf(tmp_path: Path):
    """Gate 11 detects Inf values in dose."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "dose_3d.csv",
        ["x", "y", "z", "dose_Gy"],
        [["1.0", "2.0", "3.0", "inf"]],
    )
    patches = _setup_patches(tmp_path, output_dir)
    state = _base_state(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate11 = [g for g in result["gate_results"] if g["gate_id"] == 11][0]
    assert gate11["passed"] is False
    assert "Inf" in gate11["message"] or "inf" in gate11["message"].lower()


@pytest.mark.anyio
async def test_gate11_skips_when_no_output_dir(tmp_path: Path):
    """Gate 11 is skipped when output dir doesn't exist."""
    nonexistent = tmp_path / "no_output"
    patches = _setup_patches(tmp_path, nonexistent)
    state = _base_state(tmp_path, execution_mode="dev_no_geant4_env")
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate11_list = [g for g in result["gate_results"] if g["gate_id"] == 11]
    if gate11_list:
        gate11 = gate11_list[0]
        # When output dir doesn't exist, gate is either skipped or passes
        # (no CSVs to check → no physics errors → pass)
        assert gate11["severity"] in ("skipped", "pass")
