"""Generate code as a patch using LLM with RAG context."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from agent_core.graph.state import RadiationAgentState

G4_CODE_GEN_PROMPT = """You are a Geant4 simulation code generator.

Generate a complete, minimal Geant4 simulation project based on the specification.

Specification:
{simulation_ir}

RAG Context (reference material):
{rag_context}

Requirements:
1. Generate C++ code for each module listed in the architecture plan
2. Include proper headers, using declarations, and Geant4 namespaces
3. Use G4SystemOfUnits for all physical quantities
4. Create a CMakeLists.txt with proper Geant4 linkage
5. Score energy deposition and dose in a 3D voxelized geometry
6. Output CSV files for energy deposition and dose
7. Use FTFP_BERT physics list (or as specified)
8. Generate a main entry point (geant4_sim.cc)

Output format: Return a JSON object with this structure:
{{
  "files": {{
    "path/to/file.cc": "file content here",
    "CMakeLists.txt": "file content here"
  }},
  "description": "Brief description of generated code",
  "assumptions": ["list of assumptions made"]
}}

Return ONLY the JSON object.
"""

# Minimal template constants for fallback
_MAIN_CC = '''#include "G4RunManager.hh"
#include "G4UImanager.hh"
#include "FTFP_BERT.hh"

int main() {
    G4RunManager* runManager = new G4RunManager;
    runManager->SetUserInitialization(new FTFP_BERT);
    // TODO: Add user actions
    runManager->Initialize();
    runManager->BeamOn(10);
    delete runManager;
    return 0;
}
'''

_CMAKELISTS = '''cmake_minimum_required(VERSION 3.16)
project(geant4_sim)
find_package(Geant4 REQUIRED)
add_executable(geant4_sim geant4_sim.cc)
target_link_libraries(geant4_sim Geant4::Granular)
'''


def _generate_fallback_code(sim_ir: dict) -> dict:
    """Generate minimal fallback Geant4 code when LLM is unavailable."""
    return {
        "files": {
            "geant4_sim.cc": _MAIN_CC,
            "CMakeLists.txt": _CMAKELISTS,
        },
        "description": "Minimal Geant4 simulation (fallback template)",
        "assumptions": ["Using default FTFP_BERT physics", "Fallback code without LLM"],
    }


async def write_code_patch(state: RadiationAgentState) -> dict:
    """Generate Geant4 code as a patch using LLM with RAG context."""
    sim_ir = state.get("simulation_ir", {})
    g4_context = state.get("g4_context", [])
    job_id = state.get("job_id", "unknown")

    rag_context_str = (
        json.dumps(g4_context[:5], indent=2, ensure_ascii=False)
        if g4_context
        else "No RAG context available"
    )
    sim_ir_str = json.dumps(sim_ir, indent=2, ensure_ascii=False)

    try:
        from agent_core.llm import get_llm

        llm = get_llm(temperature=0)
        prompt = G4_CODE_GEN_PROMPT.format(
            simulation_ir=sim_ir_str, rag_context=rag_context_str
        )
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        # Strip markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        code_result = json.loads(content.strip())
    except Exception:
        code_result = _generate_fallback_code(sim_ir)

    # Build patch
    files = code_result.get("files", {})
    patch = {
        "patch_id": str(uuid.uuid4()),
        "job_id": job_id,
        "description": code_result.get("description", "Generated Geant4 simulation code"),
        "change_type": "create",
        "risk_level": "low",
        "changed_files": [
            {
                "path": f"simulation_workspace/jobs/{job_id}/05_geant4/{fp}",
                "zone": "green",
                "new_content": content,
                "diff_content": "",
            }
            for fp, content in files.items()
        ],
        "test_plan": state.get("test_plan", {}).get("tests", []),
        "expected_outputs": ["edep_3d.csv", "dose_3d.csv", "event_table.csv"],
        "dependencies": ["Geant4"],
        "rollback_possible": True,
    }

    # Save patch
    job_dir = Path("simulation_workspace/jobs") / job_id
    patch_file = job_dir / "04_generated_code" / "proposed_patch.json"
    patch_file.write_text(json.dumps(patch, indent=2, ensure_ascii=False))
    changed_file = job_dir / "04_generated_code" / "changed_files.json"
    changed_file.write_text(json.dumps(list(files.keys()), indent=2))

    # Write actual code files
    g4_dir = job_dir / "05_geant4"
    for fp, content in files.items():
        file_path = g4_dir / fp
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    return {"proposed_patch": patch, "current_node": "write_code_patch"}
