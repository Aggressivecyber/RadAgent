"""Tests for the generic agent loop.

A scripted fake gateway drives the loop deterministically; one optional real
mimo call (gated by env) proves the native tool-calling round-trip end-to-end.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agent_core.agent_loop import AgentLoopResult, run_agent_loop
from agent_core.dev_tools import DevToolkit
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


class _FakeGateway:
    """Replays a script of ModelCallResult per turn."""

    def __init__(self, script: list[ModelCallResult]) -> None:
        self._script = list(script)
        self.calls = 0

    async def call(self, **kwargs):  # noqa: ANN003 - matches gateway.call shape loosely
        self.calls += 1
        if not self._script:
            pytest.fail("Fake gateway script exhausted")
        return self._script.pop(0)


def _result(*, content: str = "", tool_calls=None, error: str = "") -> ModelCallResult:
    return ModelCallResult(
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        provider=ModelProvider.OPENAI_COMPATIBLE,
        model_name="fake",
        content=content,
        tool_calls=list(tool_calls or []),
        finish_reason="tool_calls" if tool_calls else "stop",
        error=error,
    )


@pytest.mark.asyncio
async def test_loop_runs_tools_then_finishes_naturally() -> None:
    workdir = Path(tempfile.mkdtemp())
    (workdir / "a.txt").write_text("hello world\n")
    toolkit = DevToolkit(workdir)

    script = [
        _result(
            tool_calls=[
                {"id": "c1", "name": "read_file", "arguments": '{"path": "a.txt"}'},
            ]
        ),
        _result(content="Done, the file says hello."),
    ]
    gw = _FakeGateway(script)

    result = await run_agent_loop(
        gateway=gw,  # type: ignore[arg-type]
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="sys",
        user_message="read a.txt",
        toolkit=toolkit,
        max_turns=5,
    )

    assert result.stop_reason == "natural"
    assert result.n_turns == 2
    assert len(result.tool_audit) == 1
    assert result.tool_audit[0]["name"] == "read_file"
    assert result.tool_audit[0]["ok"] is True
    # The tool result must have been fed back as a role:tool message.
    assert any(m.get("role") == "tool" for m in result.messages)
    # The assistant tool_call message must be re-wrapped in provider shape.
    asst = result.messages[2]
    assert asst["role"] == "assistant"
    assert asst["tool_calls"][0]["function"]["name"] == "read_file"


@pytest.mark.asyncio
async def test_loop_dispatches_multiple_tool_calls_from_one_response() -> None:
    workdir = Path(tempfile.mkdtemp())
    toolkit = DevToolkit(workdir, tool_names=["write_file"])
    script = [
        _result(
            tool_calls=[
                {
                    "id": "c1",
                    "name": "write_file",
                    "arguments": '{"path": "a.txt", "content": "A\\n"}',
                },
                {
                    "id": "c2",
                    "name": "write_file",
                    "arguments": '{"path": "b.txt", "content": "B\\n"}',
                },
            ]
        ),
        _result(content="DONE"),
    ]
    gw = _FakeGateway(script)

    result = await run_agent_loop(
        gateway=gw,  # type: ignore[arg-type]
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="sys",
        user_message="write both files",
        toolkit=toolkit,
        max_turns=3,
    )

    assert result.stop_reason == "natural"
    assert [entry["name"] for entry in result.tool_audit] == ["write_file", "write_file"]
    assert (workdir / "a.txt").read_text(encoding="utf-8") == "A\n"
    assert (workdir / "b.txt").read_text(encoding="utf-8") == "B\n"


@pytest.mark.asyncio
async def test_loop_respects_max_turns() -> None:
    workdir = Path(tempfile.mkdtemp())
    toolkit = DevToolkit(workdir)
    # Always asks for another tool call -> never finishes naturally.
    script = [
        _result(tool_calls=[{"id": f"c{i}", "name": "run_bash", "arguments": '{"command": "true"}'}])
        for i in range(10)
    ]
    gw = _FakeGateway(script)

    result = await run_agent_loop(
        gateway=gw,  # type: ignore[arg-type]
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="sys",
        user_message="loop",
        toolkit=toolkit,
        max_turns=3,
    )
    assert result.stop_reason == "max_turns"
    assert result.n_turns == 3


@pytest.mark.asyncio
async def test_loop_stop_hook_short_circuits_on_success() -> None:
    workdir = Path(tempfile.mkdtemp())
    toolkit = DevToolkit(workdir)

    script = [
        _result(tool_calls=[{"id": "c1", "name": "run_bash", "arguments": '{"command": "true"}'}]),
        _result(content="would not reach"),
    ]
    gw = _FakeGateway(script)

    async def stop(_toolkit, audit) -> bool:  # noqa: ANN001
        return any(a["name"] == "run_bash" and a["ok"] for a in audit)

    result = await run_agent_loop(
        gateway=gw,  # type: ignore[arg-type]
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="sys",
        user_message="go",
        toolkit=toolkit,
        max_turns=5,
        stop_hook=stop,
    )
    assert result.stop_reason == "stop_hook"
    assert result.n_turns == 1


@pytest.mark.asyncio
async def test_loop_survives_tool_exception() -> None:
    workdir = Path(tempfile.mkdtemp())
    toolkit = DevToolkit(workdir)

    # read_file with missing file returns ok=False (not an exception), but
    # dispatch wraps real exceptions too. Verify the loop keeps going.
    script = [
        _result(tool_calls=[{"id": "c1", "name": "read_file", "arguments": '{"path": "nope.cc"}'}]),
        _result(content="recovered"),
    ]
    gw = _FakeGateway(script)
    result = await run_agent_loop(
        gateway=gw,  # type: ignore[arg-type]
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="sys",
        user_message="go",
        toolkit=toolkit,
        max_turns=5,
    )
    assert result.stop_reason == "natural"
    assert result.tool_audit[0]["ok"] is False  # file not found surfaced gracefully


@pytest.mark.asyncio
async def test_loop_stall_nudge_retries_text_only_responses() -> None:
    workdir = Path(tempfile.mkdtemp())
    toolkit = DevToolkit(workdir)
    # Model keeps emitting text-only (no tool call) — a stall. With a stall
    # budget of 2 the loop injects the nudge twice before giving up, mirroring
    # how agentic_repair must keep iterating instead of abandoning the task.
    script = [
        _result(content="I'm thinking about it."),
        _result(content="Still unsure."),
        _result(content="I really can't decide."),
    ]
    gw = _FakeGateway(script)
    result = await run_agent_loop(
        gateway=gw,  # type: ignore[arg-type]
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="sys",
        user_message="fix it",
        toolkit=toolkit,
        max_turns=10,
        max_stalls=2,
        stall_nudge="You must call a tool now.",
    )
    assert result.stop_reason == "natural"
    assert gw.calls == 3  # initial + 2 nudged retries
    nudge_msgs = [
        m for m in result.messages
        if m.get("role") == "user" and "must call a tool" in m.get("content", "")
    ]
    assert len(nudge_msgs) == 2


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("RADAGENT_API_KEY"),
    reason="requires real mimo API to verify native tool round-trip",
)
async def test_real_mimo_tool_round_trip_end_to_end() -> None:
    """One real mimo call through the gateway + dev toolkit, headless."""
    from agent_core.models.gateway import get_model_gateway

    workdir = Path(tempfile.mkdtemp())
    (workdir / "note.txt").write_text("the password is 42\n")
    toolkit = DevToolkit(workdir)
    gw = get_model_gateway()

    result: AgentLoopResult = await asyncio.wait_for(
        run_agent_loop(
            gateway=gw,
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt="You inspect files with read_file. When done, state the answer in one sentence.",
            user_message="Read note.txt and tell me the password.",
            toolkit=toolkit,
            max_turns=4,
            max_tokens=2048,
        ),
        timeout=120,
    )
    assert result.stop_reason == "natural"
    assert result.tool_audit, "model should have called read_file at least once"
    assert any(a["name"] == "read_file" for a in result.tool_audit)
    assert "42" in result.content
