from __future__ import annotations

from typing import Any

from agent_core.chat.agent import ChatAgent

_chat_agent: ChatAgent | None = None


async def chat_response_node(state: dict[str, Any]) -> dict[str, Any]:
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()

    user_query = str(state.get("user_query", "")).strip()
    response = await _chat_agent.chat(user_query)
    return {
        "response_text": response,
        "response_status": "answered",
        "pipeline_terminated": True,
        "current_node": "chat_response",
    }
