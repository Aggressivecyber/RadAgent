"""I/O nodes for the G4 codegen subgraph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


async def load_model_ir(state: G4CodegenSubgraphState) -> dict[str, Any]:
    """Load the persisted G4 Model IR from the path carried in subgraph state."""
    ir_path = state.get("g4_model_ir_path", "")
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text(encoding="utf-8"))
    else:
        model_ir = {}

    return {
        "g4_model_ir": model_ir,
        "errors": [],
        "retry_count": 0,
    }
