"""Tests for agentic integration repair control flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_core.agent_loop.loop import AgentLoopResult
from agent_core.models.schemas import ModelTier


@pytest.mark.asyncio
async def test_agentic_repair_uses_pro_tier_tool_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Compiler-guided repair should not default to the MAX tier."""
    from agent_core.g4_codegen import agentic_repair

    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    seen: dict[str, Any] = {}

    class FakeGateway:
        pass

    async def fake_run_agent_loop(**kwargs: Any) -> AgentLoopResult:
        seen["tier"] = kwargs["tier"]
        seen["metadata"] = kwargs["metadata"]
        return AgentLoopResult(
            content="BUILD AND SMOKE PASSED",
            stop_reason="stop_hook",
            n_turns=1,
            messages=[],
            tool_audit=[],
        )

    async def fake_runtime_gate(**_: Any) -> dict[str, Any]:
        return {"status": "pass", "errors": []}

    monkeypatch.setattr(
        "agent_core.models.gateway.get_model_gateway",
        lambda: FakeGateway(),
    )
    monkeypatch.setattr(agentic_repair, "run_agent_loop", fake_run_agent_loop)
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        fake_runtime_gate,
    )

    await agentic_repair.run_agentic_repair(
        {"changed_files": [{"path": "main.cc", "new_content": "int main(){return 0;}\n"}]},
        job_id="job_repair_tier",
        attempt_index=0,
    )

    assert seen["tier"] == ModelTier.PRO
    assert seen["metadata"]["enable_thinking"] is False
