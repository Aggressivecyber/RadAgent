from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Command:
    """A deterministic TUI command parsed from composer input."""

    name: str
    args: str = ""
    raw: str = ""


@dataclass(frozen=True)
class TimelineRow:
    """Presentation model for one transcript or execution timeline row."""

    id: str
    kind: str
    status: str
    title: str
    summary: str
    phase: str = ""
    job_id: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HeaderState:
    """Compact state rendered in the fixed TUI header."""

    project: str = "default"
    job_id: str = ""
    status: str = "idle"
    phase: str = ""
    execution_mode: str = "strict"
    run_mode: str = "strict"
    needs_confirmation: bool = False
