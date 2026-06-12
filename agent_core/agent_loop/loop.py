"""Generic native tool-calling agent loop.

Drives a model (via ``ModelGateway.call`` with OpenAI-style ``tools``) and a
:class:`~agent_core.dev_tools.DevToolkit` through a build-fix loop:

    assistant -> tool_calls -> dispatch -> tool results -> assistant -> ...

until the assistant stops calling tools (natural finish), an optional
``stop_hook`` declares success, or ``max_turns`` is exhausted.

This is the reusable core; codegen-specific glue lives in
``agent_core.g4_codegen.agentic_repair``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from agent_core.dev_tools import DevToolkit
from agent_core.models.schemas import ModelCallResult, ModelTask, ModelTier

if TYPE_CHECKING:
    from agent_core.models.gateway import ModelGateway

StopHook = Callable[[DevToolkit, list[dict[str, Any]]], Awaitable[bool]]
NudgeHook = Callable[[list[dict[str, Any]]], str | None]


@dataclass
class AgentLoopResult:
    """Outcome of an agent loop run."""

    content: str
    stop_reason: str  # "natural" | "stop_hook" | "max_turns" | "error" | "empty"
    n_turns: int
    messages: list[dict[str, Any]]
    tool_audit: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


async def run_agent_loop(
    *,
    gateway: ModelGateway,
    task: ModelTask,
    tier: ModelTier,
    system_prompt: str,
    user_message: str,
    toolkit: DevToolkit,
    max_turns: int = 12,
    max_tokens: int = 8192,
    stop_hook: StopHook | None = None,
    nudge_hook: NudgeHook | None = None,
    metadata: dict[str, Any] | None = None,
    max_stalls: int = 0,
    stall_nudge: str | None = None,
) -> AgentLoopResult:
    """Run the tool-calling loop and return the final state + audit trail."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tool_audit: list[dict[str, Any]] = []
    base_meta = dict(metadata or {})
    stalls = 0

    for turn in range(max_turns):
        res: ModelCallResult = await gateway.call(
            task=task,
            tier=tier,
            system_prompt="",
            user_prompt="",
            messages=messages,
            tools=toolkit.schemas,
            max_tokens=max_tokens,
            metadata={**base_meta, "agent_turn": turn, "agent_tool_calls_so_far": len(tool_audit)},
        )
        if res.error:
            return AgentLoopResult(
                content="",
                stop_reason="error",
                n_turns=turn,
                messages=messages,
                tool_audit=tool_audit,
                error=res.error,
            )

        messages.append(_assistant_message(res))

        if not res.tool_calls:
            # The model produced a response with no tool call. For
            # task-oriented loops (e.g. agentic repair) this usually means the
            # model gave up instead of fixing the error. When a stall budget is
            # configured, inject a forceful nudge and keep going rather than
            # abandoning the task on the first text-only response.
            if stalls < max_stalls and stall_nudge:
                stalls += 1
                messages.append(
                    {"role": "user", "content": stall_nudge}
                )
                continue
            return AgentLoopResult(
                content=res.content,
                stop_reason="natural" if res.content.strip() else "empty",
                n_turns=turn + 1,
                messages=messages,
                tool_audit=tool_audit,
            )

        for call in res.tool_calls:
            result = await toolkit.dispatch(call.get("name", ""), call.get("arguments", ""))
            tool_audit.append(
                {
                    "turn": turn,
                    "id": call.get("id", ""),
                    "name": call.get("name", ""),
                    "arguments": call.get("arguments", ""),
                    "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
                    "result": result,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": call.get("name", ""),
                    "content": _stringify_tool_result(result),
                }
            )

        if nudge_hook is not None:
            nudge = nudge_hook(tool_audit)
            if nudge:
                messages.append({"role": "user", "content": nudge})

        if stop_hook is not None and await stop_hook(toolkit, tool_audit):
            return AgentLoopResult(
                content=res.content,
                stop_reason="stop_hook",
                n_turns=turn + 1,
                messages=messages,
                tool_audit=tool_audit,
            )

    return AgentLoopResult(
        content="",
        stop_reason="max_turns",
        n_turns=max_turns,
        messages=messages,
        tool_audit=tool_audit,
    )


def _assistant_message(res: ModelCallResult) -> dict[str, Any]:
    """Re-wrap a gateway result into the provider assistant message shape.

    OpenAI-compatible APIs require the assistant message to carry back the
    ``tool_calls`` it emitted. The gateway normalizes tool_calls to
    ``{id, name, arguments}``; re-wrap into ``{id, type, function:{...}}``.
    """
    msg: dict[str, Any] = {"role": "assistant"}
    if res.content:
        msg["content"] = res.content
    if res.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.get("id", "") or f"call_{i}",
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": tc.get("arguments", ""),
                },
            }
            for i, tc in enumerate(res.tool_calls)
        ]
    return msg


def _stringify_tool_result(result: Any) -> str:
    """Tool results become ``role: tool`` message content — must be a string."""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(result)
    # Keep the feedback bounded so the loop does not blow the context window.
    if len(text) > 16_000:
        text = text[:16_000] + "\n...[truncated]"
    return text
