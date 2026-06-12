"""Generic native tool-calling agent loop — package re-exports.

Implementation lives in :mod:`agent_core.agent_loop.loop` (package
``__init__.py`` must not define business functions per the architecture rule).
"""

from __future__ import annotations

from agent_core.agent_loop.loop import AgentLoopResult, run_agent_loop

__all__ = ["AgentLoopResult", "run_agent_loop"]
