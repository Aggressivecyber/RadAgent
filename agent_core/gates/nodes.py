"""Gate Validation Subgraph nodes — re-exports from split modules.

The gate system is organized into:
- base_gates.py — Gate 0-11 (context, schema, build, simulation)
- g4_modeling_gates.py — G4-A to G4-G (complex model validation)
- gate_runner.py — orchestration (load inputs, finalize results)
- failure_classifier.py — maps failed gates to retry subgraphs

This module re-exports all public functions for backward compatibility.
"""

from __future__ import annotations

from .base_gates import gate_name as _gate_name
from .base_gates import run_base_gates
from .failure_classifier import (
    classify_failure,
    classify_failures_by_gate_names,
    get_failure_summary,
)
from .g4_modeling_gates import run_g4_modeling_gates
from .gate_runner import (
    finalize_gate_results,
    load_gate_inputs,
)

# Backward-compatible alias used by tests
_gate_name = _gate_name

__all__ = [
    "load_gate_inputs",
    "run_base_gates",
    "run_g4_modeling_gates",
    "finalize_gate_results",
    "_gate_name",
    "classify_failure",
    "classify_failures_by_gate_names",
    "get_failure_summary",
]
