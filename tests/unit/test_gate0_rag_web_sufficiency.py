"""Gate 0 — RAG+Web context sufficiency tests.

Validates the three-state context decision model:
  allow_rag / allow_with_web_supplement / block_no_context
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from agent_core.nodes.run_gate_checks import run_gate_checks


def _valid_patch() -> dict:
    """Return a patch that passes PatchValidator."""
    return {
        "patch_id": "p1",
        "job_id": "test-job",
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


def _base_state(**overrides: object) -> dict:
    """Minimal state dict that won't crash gate checks."""
    return {
        "job_id": "test-job",
        "user_query": "10 MeV proton",
        "execution_mode": "dev_no_geant4_env",
        "task_spec": {},
        "simulation_ir": {},
        "proposed_patch": _valid_patch(),
        "rag_sufficiency_score": 0.0,
        "context_decision": "block_no_context",
        "context_sufficiency_report": {},
        "web_search_available": False,
        "skipped_gates": [],
        **overrides,
    }


def _setup_patches(tmp_path: Path) -> list:
    """Return context managers for workspace patches."""
    (tmp_path / "09_validation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "05_geant4" / "src").mkdir(parents=True, exist_ok=True)
    return [
        patch("agent_core.nodes.run_gate_checks.get_output_dir", return_value=tmp_path),
        patch("agent_core.nodes.run_gate_checks.get_job_dir", return_value=tmp_path),
    ]


@pytest.mark.anyio
async def test_gate0_allow_rag_passes(tmp_path: Path):
    """Gate 0 passes with severity=pass when context_decision=allow_rag."""
    state = _base_state(
        context_decision="allow_rag",
        rag_sufficiency_score=0.95,
    )
    patches = _setup_patches(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate0 = result["gate_results"][0]
    assert gate0["gate_id"] == 0
    assert gate0["passed"] is True
    assert gate0["severity"] == "pass"
    assert "RAG" in gate0["message"]


@pytest.mark.anyio
async def test_gate0_web_supplement_warns(tmp_path: Path):
    """Gate 0 passes with severity=warning when web supplements RAG."""
    state = _base_state(
        context_decision="allow_with_web_supplement",
        rag_sufficiency_score=0.65,
        context_sufficiency_report={
            "web_urls": ["https://example.com/physics"],
        },
    )
    patches = _setup_patches(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate0 = result["gate_results"][0]
    assert gate0["passed"] is True
    assert gate0["severity"] == "warning"
    assert "web search" in gate0["message"].lower() or "Web" in gate0["message"]


@pytest.mark.anyio
async def test_gate0_block_no_context_blocks(tmp_path: Path):
    """Gate 0 blocks when context_decision=block_no_context."""
    state = _base_state(
        context_decision="block_no_context",
        rag_sufficiency_score=0.30,
        web_search_available=False,
    )
    patches = _setup_patches(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate0 = result["gate_results"][0]
    assert gate0["passed"] is False
    assert gate0["severity"] == "block"


@pytest.mark.anyio
async def test_gate0_block_reports_web_insufficient(tmp_path: Path):
    """When web was tried but insufficient, message mentions it."""
    state = _base_state(
        context_decision="block_no_context",
        rag_sufficiency_score=0.20,
        web_search_available=True,
    )
    patches = _setup_patches(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate0 = result["gate_results"][0]
    assert gate0["passed"] is False
    assert "insufficient" in gate0["message"].lower()


@pytest.mark.anyio
async def test_gate0_unknown_decision_fails(tmp_path: Path):
    """Unknown context_decision results in severity=fail."""
    state = _base_state(context_decision="maybe_perhaps")
    patches = _setup_patches(tmp_path)
    for p in patches:
        p.start()
    try:
        result = await run_gate_checks(state)
    finally:
        for p in patches:
            p.stop()
    gate0 = result["gate_results"][0]
    assert gate0["passed"] is False
    assert gate0["severity"] == "fail"
    assert "Unknown" in gate0["message"]
