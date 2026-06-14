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
import re
from collections import defaultdict
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
    repeated_tool_result_limit: int = 0,
    max_history_chars: int | None = None,
    preserve_recent_tool_messages: int = 2,
) -> AgentLoopResult:
    """Run the tool-calling loop and return the final state + audit trail."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    tool_audit: list[dict[str, Any]] = []
    base_meta = dict(metadata or {})
    stalls = 0
    repeated_failures: dict[str, int] = defaultdict(int)

    for turn in range(max_turns):
        prompt_messages = _compact_messages_for_prompt(
            messages,
            max_history_chars=max_history_chars,
            preserve_recent_tool_messages=preserve_recent_tool_messages,
        )
        res: ModelCallResult = await gateway.call(
            task=task,
            tier=tier,
            system_prompt="",
            user_prompt="",
            messages=prompt_messages,
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
            if repeated_tool_result_limit > 0:
                fingerprint = _tool_failure_fingerprint(call.get("name", ""), result)
                if fingerprint:
                    repeated_failures[fingerprint] += 1
                    if repeated_failures[fingerprint] >= repeated_tool_result_limit:
                        return AgentLoopResult(
                            content=res.content,
                            stop_reason="stalled_repeated_tool_result",
                            n_turns=turn + 1,
                            messages=messages,
                            tool_audit=tool_audit,
                            error=(
                                "Repeated failing tool result "
                                f"{repeated_failures[fingerprint]}x: {fingerprint}"
                            ),
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


def _compact_messages_for_prompt(
    messages: list[dict[str, Any]],
    *,
    max_history_chars: int | None,
    preserve_recent_tool_messages: int,
) -> list[dict[str, Any]]:
    """Return a provider-facing copy with old tool payloads summarized.

    Tool-call APIs need the assistant/tool message structure to remain intact,
    so compaction replaces only bulky tool content. The full tool results remain
    in ``tool_audit`` for reporting and debugging.
    """
    if max_history_chars is None or max_history_chars <= 0:
        return messages
    if _message_content_chars(messages) <= max_history_chars:
        return messages

    compacted = [_copy_message_for_prompt(message) for message in messages]
    tool_indices = [
        index for index, message in enumerate(compacted) if message.get("role") == "tool"
    ]
    preserve_count = max(0, int(preserve_recent_tool_messages or 0))
    preserved = set(tool_indices[-preserve_count:]) if preserve_count else set()

    for index in tool_indices:
        if index in preserved:
            continue
        content = str(compacted[index].get("content", ""))
        compacted[index]["content"] = _compact_tool_message_content(content, max_chars=1_200)

    _compact_assistant_tool_call_arguments(compacted, max_chars=1_200)

    if _message_content_chars(compacted) <= max_history_chars:
        return compacted

    for index in tool_indices:
        if index in preserved:
            continue
        content = str(compacted[index].get("content", ""))
        compacted[index]["content"] = _compact_tool_message_content(content, max_chars=500)

    _compact_assistant_tool_call_arguments(compacted, max_chars=500)

    if _message_content_chars(compacted) <= max_history_chars:
        return compacted

    for index in tool_indices:
        content = str(compacted[index].get("content", ""))
        compacted[index]["content"] = _compact_tool_message_content(content, max_chars=280)

    _compact_assistant_tool_call_arguments(compacted, max_chars=280)

    return compacted


def _copy_message_for_prompt(message: dict[str, Any]) -> dict[str, Any]:
    copied = dict(message)
    if "tool_calls" not in copied:
        return copied
    tool_calls: list[Any] = []
    for tool_call in copied.get("tool_calls") or []:
        if not isinstance(tool_call, dict):
            tool_calls.append(tool_call)
            continue
        copied_tool_call = dict(tool_call)
        function = copied_tool_call.get("function")
        if isinstance(function, dict):
            copied_tool_call["function"] = dict(function)
        tool_calls.append(copied_tool_call)
    copied["tool_calls"] = tool_calls
    return copied


def _compact_assistant_tool_call_arguments(
    messages: list[dict[str, Any]],
    *,
    max_chars: int,
) -> None:
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict):
                continue
            arguments = str(function.get("arguments", ""))
            if len(arguments) <= max_chars:
                continue
            function["arguments"] = _compact_tool_call_arguments(
                str(function.get("name", "")),
                arguments,
                max_chars=max_chars,
            )


def _compact_tool_call_arguments(name: str, arguments: str, *, max_chars: int) -> str:
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        parsed = None

    summary: dict[str, Any] = {
        "compacted_previous_tool_call": name or "tool",
        "original_argument_chars": len(arguments),
    }
    if isinstance(parsed, dict):
        for key in ("path", "command", "old_string", "new_string", "content"):
            if key not in parsed:
                continue
            value = str(parsed.get(key, ""))
            if key in {"content", "old_string", "new_string"}:
                summary[f"{key}_chars"] = len(value)
            else:
                summary[key] = _clip_middle(value, max_chars=240)
        remaining_keys = sorted(
            str(key) for key in parsed.keys()
            if key not in {"path", "command", "old_string", "new_string", "content"}
        )
        if remaining_keys:
            summary["other_keys"] = remaining_keys[:12]
    else:
        summary["arguments_excerpt"] = _clip_middle(arguments, max_chars=240)

    text = json.dumps(summary, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    summary.pop("other_keys", None)
    text = json.dumps(summary, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 17)] + "...[compacted]"


def _message_content_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += len(str(message.get("content", "")))
        if message.get("tool_calls"):
            total += len(json.dumps(message.get("tool_calls"), ensure_ascii=False))
    return total


def _compact_tool_message_content(content: str, *, max_chars: int) -> str:
    parsed: Any
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        parsed = None

    source = content
    summary: dict[str, Any] = {"status": "compacted previous tool result"}
    if isinstance(parsed, dict):
        for key in ("ok", "stage", "exit_code", "error"):
            if key in parsed:
                summary[key] = parsed.get(key)
        source = str(
            parsed.get("output")
            or parsed.get("errors")
            or parsed.get("stderr")
            or parsed.get("stdout")
            or content
        )

    diagnostics = _extract_diagnostic_lines(source, max_lines=8)
    if diagnostics:
        summary["diagnostics"] = diagnostics
    else:
        summary["excerpt"] = _clip_middle(source, max_chars=max(80, max_chars // 2))

    text = json.dumps(summary, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    summary["diagnostics"] = _extract_diagnostic_lines(source, max_lines=3)
    if not summary.get("diagnostics"):
        summary["excerpt"] = _clip_middle(source, max_chars=120)
    text = json.dumps(summary, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 17)] + "...[compacted]"


def _extract_diagnostic_lines(text: str, *, max_lines: int) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text).splitlines():
        line = _normalize_diagnostic_line(raw_line)
        if not line:
            continue
        if any(
            token in line
            for token in (
                " error:",
                "fatal error:",
                "warning:",
                "G4Exception",
                "Missing output",
                "not declared",
                "no matching function",
                "undefined reference",
            )
        ):
            lines.append(line)
        if len(lines) >= max_lines:
            break
    if lines:
        return lines
    return [_normalize_diagnostic_line(line) for line in str(text).splitlines()[:max_lines] if line.strip()]


def _clip_middle(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 20:
        return text[:max_chars]
    head = max_chars // 2
    tail = max_chars - head - 15
    return text[:head] + "\n...[omitted]...\n" + text[-max(0, tail):]


def _tool_failure_fingerprint(name: str, result: Any) -> str:
    """Return a compact stable fingerprint for repeated failing tool outputs."""
    if not isinstance(result, dict) or result.get("ok") is not False:
        return ""
    raw = str(result.get("output") or result.get("error") or result)
    if not raw.strip():
        return str(name)
    lines: list[str] = []
    for line in raw.splitlines():
        normalized = _normalize_diagnostic_line(line)
        if not normalized:
            continue
        if any(token in normalized for token in (" error:", "fatal error:", "G4Exception", "Missing output")):
            lines.append(normalized)
        if len(lines) >= 4:
            break
    if not lines:
        lines = [_normalize_diagnostic_line(raw)[:240]]
    return f"{name}: " + " | ".join(lines)


def _normalize_diagnostic_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    # Absolute attempt directories change across runs; keep source-relative
    # paths and line diagnostics stable.
    line = re.sub(r"/[^:\s]*/geant4_project/", "", line)
    line = re.sub(r"runtime_attempt_\d+", "runtime_attempt_N", line)
    line = re.sub(r":\d+:\d+:", ":N:N:", line)
    line = re.sub(r":\d+:", ":N:", line)
    line = re.sub(r"\s+", " ", line)
    return line[:300]
