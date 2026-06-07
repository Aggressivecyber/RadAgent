"""Shared prompt templates for the model gateway."""

from __future__ import annotations

JSON_OUTPUT_INSTRUCTION = (
    "You must output ONLY valid JSON. No markdown, no explanation, "
    "no code fences. Just the raw JSON object."
)
