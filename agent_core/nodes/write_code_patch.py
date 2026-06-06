"""Generate code as a patch using LLM with RAG context.

Fix 2: Only writes proposed_patch.json to 04_generated_code/.
        Actual file writes are delegated to apply_patch node.
Fix 4: LLM prompt instructs proper output directory usage.
Fix 7: No silent fallback — failures propagate to classify_failure.
"""

from __future__ import annotations

import json
import logging
import uuid

from agent_core.config.workspace import get_job_dir, get_output_dir
from agent_core.graph.state import RadiationAgentState

logger = logging.getLogger(__name__)

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
9. The program must read the output directory from the G4_OUTPUT_DIR environment
   variable (fallback to "./output" if not set).
10. The program must read the job ID from the G4_JOB_ID environment variable.
11. At the end of the run, write these files to G4_OUTPUT_DIR:
    - edep_3d.csv: voxelized energy deposition (columns: ix,iy,iz,edep_MeV)
    - dose_3d.csv: voxelized dose (columns: ix,iy,iz,dose_Gy)
    - event_table.csv: per-event summary (columns: event_id,primary_particle,total_edep_MeV)
    - g4_summary.json: {{"particle": ..., "energy_MeV": ...,
        "events": ..., "geometry": ..., "physics_list": ...}}
    - provenance.json: {{"simulation_id": ..., "geant4_version": ...,
        "physics_list": ..., "random_seed": ..., "generated_at": ..., "code_hash": ...}}
12. Use bare filenames (e.g. "DetectorConstruction.cc", NOT "src/DetectorConstruction.cc").
    The build system will place them in the correct directories.

Output format: Return a JSON object with this structure:
{{
  "files": {{
    "DetectorConstruction.cc": "file content here",
    "DetectorConstruction.hh": "file content here",
    "geant4_sim.cc": "file content here",
    "CMakeLists.txt": "file content here"
  }},
  "description": "Brief description of generated code",
  "assumptions": ["list of assumptions made"]
}}

Return ONLY the JSON object. Use bare filenames, no directory prefixes.
"""


def _map_to_geant4_layout(files: dict[str, str]) -> list[dict]:
    """Map flat filenames to proper Geant4 project layout.

    - *.cc (except geant4_sim.cc) → 05_geant4/src/{name}
    - *.hh → 05_geant4/include/{name}
    - geant4_sim.cc, CMakeLists.txt → 05_geant4/{name}
    - Everything else → 05_geant4/{name}
    """
    root_files = {"geant4_sim.cc", "CMakeLists.txt", "CMakeLists.txt.in"}
    changed: list[dict] = []

    for filename, content in files.items():
        if filename in root_files:
            rel_path = f"05_geant4/{filename}"
        elif filename.endswith(".cc"):
            rel_path = f"05_geant4/src/{filename}"
        elif filename.endswith(".hh") or filename.endswith(".h"):
            rel_path = f"05_geant4/include/{filename}"
        elif filename.endswith(".mac"):
            rel_path = f"05_geant4/macros/{filename}"
        else:
            rel_path = f"05_geant4/{filename}"

        changed.append({
            "path": rel_path,
            "zone": "green",
            "new_content": content,
            "diff_content": "",
        })

    return changed


async def write_code_patch(state: RadiationAgentState) -> dict:
    """Generate Geant4 code as a patch using LLM with RAG context.

    Only writes proposed_patch.json to 04_generated_code/.
    Actual code files are written by apply_patch node.

    MVP-1 scope guard: Only generates Geant4 code. TCAD/SPICE simulation
    scopes are reserved for later MVPs and will not produce code patches.
    """
    sim_ir = state.get("simulation_ir", {})
    g4_context = state.get("g4_context", [])
    job_id = state.get("job_id", "unknown")

    # MVP-1 scope guard: block TCAD/SPICE code generation
    task_spec = state.get("task_spec", {})
    simulation_scope = task_spec.get("simulation_scope", ["geant4"])
    mvp1_blocked = [s for s in simulation_scope if s not in ("geant4",)]
    if mvp1_blocked:
        blocked_names = ", ".join(mvp1_blocked)
        return {
            "proposed_patch": {},
            "errors": [
                f"[MVP-1 Scope Guard] Code generation blocked for: {blocked_names}. "
                f"TCAD/SPICE code generation is reserved for later MVPs. "
                f"RAG retrieval and reporting are allowed, but no code will be generated.",
            ],
            "current_node": "write_code_patch",
        }

    rag_context_str = (
        json.dumps(g4_context[:5], indent=2, ensure_ascii=False)
        if g4_context
        else "No RAG context available"
    )
    sim_ir_str = json.dumps(sim_ir, indent=2, ensure_ascii=False)

    code_result: dict | None = None
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
    except Exception as exc:
        logger.warning("LLM code generation failed: %s", exc)
        # Fix 7: Do NOT silently fall back to a useless stub.
        # Return empty patch → Gate 3 (Patch Format) fails → classify_failure.
        return {
            "proposed_patch": {},
            "errors": [f"Code generation failed: {exc}"],
            "current_node": "write_code_patch",
        }

    # Build patch with proper file layout
    files = code_result.get("files", {})
    if not files:
        return {
            "proposed_patch": {},
            "errors": ["LLM returned empty files dict"],
            "current_node": "write_code_patch",
        }

    output_dir = str(get_output_dir(job_id))
    patch = {
        "patch_id": str(uuid.uuid4()),
        "job_id": job_id,
        "description": code_result.get("description", "Generated Geant4 simulation code"),
        "change_type": "create",
        "risk_level": "low",
        "changed_files": _map_to_geant4_layout(files),
        "test_plan": state.get("test_plan", {}).get("tests", []),
        "expected_outputs": [
            "g4_summary.json", "edep_3d.csv", "dose_3d.csv",
            "event_table.csv", "provenance.json",
        ],
        "dependencies": ["Geant4"],
        "rollback_possible": True,
        "output_dir": output_dir,
    }

    # Fix 2: Only save patch metadata, NOT actual code files
    job_dir = get_job_dir(job_id)
    patch_file = job_dir / "04_generated_code" / "proposed_patch.json"
    patch_file.write_text(json.dumps(patch, indent=2, ensure_ascii=False))
    changed_file = job_dir / "04_generated_code" / "changed_files.json"
    changed_file.write_text(json.dumps(list(files.keys()), indent=2))

    return {"proposed_patch": patch, "current_node": "write_code_patch"}
