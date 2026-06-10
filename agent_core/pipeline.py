"""Canonical pipeline phase ordering for RadAgent frontends and runners."""

from __future__ import annotations

from typing import Literal

PipelinePhase = Literal[
    "prepare_workspace",
    "context",
    "task_planning",
    "g4_modeling",
    "human_confirmation",
    "g4_codegen",
    "patch",
    "gate",
    "artifact",
    "report",
]

PIPELINE_PHASES: tuple[PipelinePhase, ...] = (
    "prepare_workspace",
    "context",
    "task_planning",
    "g4_modeling",
    "human_confirmation",
    "g4_codegen",
    "patch",
    "gate",
    "artifact",
    "report",
)

INTERACTIVE_PHASES: frozenset[PipelinePhase] = frozenset({"human_confirmation"})
AUTO_PHASES: frozenset[PipelinePhase] = frozenset(
    phase for phase in PIPELINE_PHASES if phase not in INTERACTIVE_PHASES
)
