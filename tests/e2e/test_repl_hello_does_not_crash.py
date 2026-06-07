"""E2E test: REPL with '你好' should not crash."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.intent.schemas import IntentResult
from agent_core.repl import RadAgentREPL


@pytest.fixture
def repl() -> RadAgentREPL:
    """Create a RadAgentREPL instance with mocked console."""
    r = RadAgentREPL(execution_mode="dev_no_geant4_env")
    r.console = MagicMock()
    return r


@pytest.mark.asyncio
async def test_repl_hello_does_not_crash(repl: RadAgentREPL) -> None:
    """REPL should handle '你好' without crashing."""
    mock_intent = IntentResult(
        intent="smalltalk",
        confidence=0.99,
        routing_reason="test",
        normalized_user_query="你好",
    )

    with patch(
        "agent_core.intent.router.classify_intent_with_lite_model",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ):
        # Should not raise
        await repl.handle_input("你好")

    # Console should have been called (response printed)
    repl.console.print.assert_called()


@pytest.mark.asyncio
async def test_repl_help_does_not_crash(repl: RadAgentREPL) -> None:
    """REPL should handle '你能做什么' without crashing."""
    mock_intent = IntentResult(
        intent="help",
        confidence=0.9,
        routing_reason="test",
        normalized_user_query="你能做什么",
    )

    with patch(
        "agent_core.intent.router.classify_intent_with_lite_model",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ):
        # Should not raise
        await repl.handle_input("你能做什么")

    # Console should have been called (help printed)
    repl.console.print.assert_called()


@pytest.mark.asyncio
async def test_repl_unknown_does_not_crash(repl: RadAgentREPL) -> None:
    """REPL should handle unknown input without crashing."""
    mock_intent = IntentResult(
        intent="unknown",
        confidence=0.4,
        routing_reason="test",
        normalized_user_query="今天天气怎么样",
        requires_clarification=True,
    )

    with patch(
        "agent_core.intent.router.classify_intent_with_lite_model",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ):
        # Should not raise
        await repl.handle_input("今天天气怎么样")

    # Console should have been called (clarification printed)
    repl.console.print.assert_called()


@pytest.mark.asyncio
async def test_repl_simulation_request_calls_cmd_run(
    repl: RadAgentREPL
) -> None:
    """REPL should call cmd_run for simulation requests."""
    mock_intent = IntentResult(
        intent="simulation_request",
        confidence=0.95,
        routing_reason="test",
        normalized_user_query="建立探测器",
        requires_job=True,
        requires_simulation_pipeline=True,
    )

    with (
        patch(
            "agent_core.intent.router.classify_intent_with_lite_model",
            new_callable=AsyncMock,
            return_value=mock_intent,
        ),
        patch.object(repl, "cmd_run", new_callable=AsyncMock) as mock_run,
    ):
        await repl.handle_input("建立一个9组件硅探测器")

    mock_run.assert_called_once_with("建立一个9组件硅探测器")
