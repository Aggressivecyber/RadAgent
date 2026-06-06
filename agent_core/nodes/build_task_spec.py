"""Build TaskSpec from user query using LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent_core.graph.state import RadiationAgentState

TASK_SPEC_PROMPT = """You are a radiation simulation task parser.

Given the user's request, produce a JSON task specification with this structure:
{
  "simulation_scope": ["geant4"],
  "particle": {"type": "proton", "energy_MeV": 10.0, "direction": [0, 0, 1], "events": 1000},
  "target": {"material": "Si", "size_um": [1000.0, 1000.0, 300.0], "geometry_type": "box"},
  "outputs": ["energy_deposition", "dose_distribution"],
  "metadata": {"source": "user_query"}
}

Rules:
- simulation_scope must include "geant4" if any particle/geometry/dose is mentioned
- simulation_scope must include "tcad" if device/defect/trap/leakage is mentioned
- simulation_scope must include "spice" if circuit/netlist/inverter is mentioned
- particle type must be a valid particle name (proton, neutron, electron, gamma, alpha, etc.)
- energy must be in MeV
- size must be in micrometers
- events defaults to 1000 for testing
- Return ONLY the JSON, no other text.

User request: {user_query}
"""


def _heuristic_parse(query: str) -> dict:
    """Fallback heuristic parser when LLM is unavailable."""
    scope = ["geant4"]
    particle = {
        "type": "proton",
        "energy_MeV": 10.0,
        "direction": [0, 0, 1],
        "events": 1000,
    }
    target = {
        "material": "Si",
        "size_um": [1000.0, 1000.0, 300.0],
        "geometry_type": "box",
    }
    outputs = ["energy_deposition", "dose_distribution"]

    # Try to extract energy
    energy_match = re.search(r"(\d+(?:\.\d+)?)\s*MeV", query)
    if energy_match:
        particle["energy_MeV"] = float(energy_match.group(1))

    # Try to extract particle type
    for p_type in ["proton", "neutron", "electron", "gamma", "alpha", "ion"]:
        if p_type in query.lower():
            particle["type"] = p_type
            break

    # Try to extract material
    for mat in ["Si", "Silicon", "GaAs", "Ge", "SiO2"]:
        if mat.lower() in query.lower():
            target["material"] = "Si" if mat.lower() == "silicon" else mat
            break

    # Try to extract thickness
    thickness_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:um|微米)", query)
    if thickness_match:
        target["size_um"][2] = float(thickness_match.group(1))

    return {
        "simulation_scope": scope,
        "particle": particle,
        "target": target,
        "outputs": outputs,
        "metadata": {"source": "heuristic_parser"},
    }


async def build_task_spec(state: RadiationAgentState) -> dict:
    """Build task specification from user query using LLM."""
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")

    try:
        from agent_core.llm import get_llm

        llm = get_llm(temperature=0)
        prompt = TASK_SPEC_PROMPT.format(user_query=user_query)
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # Strip markdown code blocks if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        task_spec = json.loads(content.strip())
    except Exception:
        # Fallback: simple heuristic parsing
        task_spec = _heuristic_parse(user_query)

    # Save task spec
    job_dir = Path("simulation_workspace/jobs") / job_id
    spec_file = job_dir / "02_task_spec" / "task_spec.json"
    spec_file.write_text(json.dumps(task_spec, indent=2, ensure_ascii=False))

    return {"task_spec": task_spec, "current_node": "build_task_spec"}
