"""Shell dev tools: run_bash (sandboxed), build_project, run_smoke.

build_project / run_smoke wrap the hardened ``Geant4Runner`` so the model gets
clean structured compile/runtime feedback. run_bash is a freeform fallback.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

DEFAULT_BASH_TIMEOUT = 120


async def run_bash(project_dir: Path, command: str, *, timeout: int = DEFAULT_BASH_TIMEOUT) -> dict[str, Any]:
    """Run a shell command in ``project_dir`` with timeout and captured output."""
    if not str(command).strip():
        return {"ok": False, "error": "Empty command."}
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return {"ok": False, "error": f"Failed to spawn: {exc}"}

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=max(1, int(timeout)))
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "ok": False,
            "error": f"Command timed out after {timeout}s.",
            "exit_code": None,
        }

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
    }


async def build_project(project_dir: Path, *, threads: int = 4) -> dict[str, Any]:
    """cmake configure (only if needed) + incremental make.

    Returns the COMPLETE raw compiler output (stdout+stderr, tail-capped) as
    plain text — including gcc carets (``^~~~~``), ``note:`` suggestions, and
    template context. This is exactly what a human reads from ``make``; do NOT
    pre-filter it or the model loses the most useful diagnostics.
    """
    from agent_core.tools.geant4_runner import Geant4Runner

    runner = Geant4Runner()
    build_dir = project_dir / "build"
    runner.prepare_build_dir(str(project_dir), str(build_dir))

    needs_configure = not (build_dir / "CMakeCache.txt").exists()
    if needs_configure:
        cfg = await runner.configure(str(project_dir), str(build_dir))
        if not cfg.get("success"):
            return {
                "ok": False,
                "stage": "configure",
                "output": f"{cfg.get('cmake_output', '')}\n{cfg.get('errors', '')}",
            }

    build = await runner.build(str(build_dir), threads=threads)
    raw = f"{build.get('build_output', '')}\n{build.get('errors', '')}"
    return {
        "ok": bool(build.get("success")),
        "stage": "build",
        "output": _known_fix_hints(raw),
        "executable_path": build.get("executable_path"),
    }


# Classic Geant4 runtime/compile errors whose fix is deterministic and
# well-known. Appending the fix to the raw feedback lets the repair agent
# apply it directly instead of re-deriving it every run — this is what makes
# the loop converge on LLM-variance errors that rotate across runs.
_KNOWN_GEANT4_FIXES: tuple[tuple[str, str], ...] = (
    (
        "Particle '", " not found in particle table",
        "PARTICLE-TABLE FIX: G4ParticleTable is not populated when "
        "PrimaryGeneratorAction is constructed, so FindParticle(name) returns "
        "null and aborts. Resolve the particle via its Definition() singleton "
        "(G4Electron::ElectronDefinition(), G4Proton::Proton(), "
        "G4Gamma::GammaDefinition()) which is always available, or look it up "
        "lazily inside GeneratePrimaries(). Never rely on FindParticle in the "
        "constructor without a Definition() fallback.",
    ),
    (
        "GeomMgt0002", "already set as",
        "REGION FIX: a logical volume cannot be the root of two regions. The "
        "world LV is already the root of DefaultRegionForTheWorld, so do NOT "
        "create a custom G4Region rooted at the world. Remove that region "
        "creation, or register only non-world scoring volumes / reuse the "
        "default region.",
    ),
    (
        "Geom0003", "Volume overlap detected",
        "OVERLAP FIX: a daughter volume is not fully inside its mother. G4Box "
        "takes HALF-lengths (pass full_dimension/2). Verify arithmetically "
        "that daughter center +/- half-length lies within the mother's bounds "
        "on every axis; fix the placement coordinates or the dimensions.",
    ),
    (
        "No material associated to the logical volume", "GetMass",
        "MATERIAL FIX: a logical volume was created with a null material — "
        "MaterialRegistry/NIST lookup failed for its material_id, then "
        "G4LogicalVolume::GetMass() aborted. Verify the NIST name is valid and "
        "spelled exactly (e.g. G4_PLASTIC_SC_VINYLENE, not G4_PLASTIC_SC_VINYL; "
        "G4_POLYSTYRENE is a safe fallback) and that GetMaterial() returns "
        "non-null BEFORE constructing the logical volume. A null material must "
        "be a hard error, not silently passed to G4LogicalVolume.",
    ),
    (
        "does not have a valid material pointer", "Logical volume <",
        "MATERIAL FIX: a G4LogicalVolume was constructed with a null material "
        "pointer. For the world volume, build or fetch G4_Galactic with "
        "G4NistManager::FindOrBuildMaterial(\"G4_Galactic\") before creating "
        "WorldLV; for detector volumes, verify each IR material_id maps to a "
        "valid NIST name in MaterialRegistry. Never pass nullptr to "
        "G4LogicalVolume; fail immediately or use a valid explicit fallback.",
    ),
    (
        "no declaration matches", "OutputManager::WriteSummaryJson()",
        "OUTPUTMANAGER SIGNATURE FIX: OutputManager.cc defines a no-argument "
        "WriteSummaryJson() that OutputManager.hh does not declare. Remove the "
        "stray empty overload and keep the declared WriteSummaryJson(G4int) "
        "definition; do not add a new unused declaration to the header.",
    ),
    (
        "G4ParticleTable::GetParticleTable()", "incomplete type",
        "PARTICLE-TABLE INCLUDE FIX: code calls G4ParticleTable methods while "
        "only seeing a forward declaration. Add #include \"G4ParticleTable.hh\" "
        "to the source file using G4ParticleTable::GetParticleTable().",
    ),
    (
        "G4Material", "has not been declared",
        "GEANT4 INCLUDE FIX: a header/source uses G4Material* without including "
        "\"G4Material.hh\". Add the include before editing signatures; the "
        "compiler may display the missing type as int* in downstream notes.",
    ),
    (
        "G4VSolid", "incomplete type",
        "GEANT4 INCLUDE FIX: a source calls methods on G4VSolid through a "
        "forward declaration. Add #include \"G4VSolid.hh\" before changing "
        "scoring or geometry logic.",
    ),
)


def _known_fix_hints(raw_output: str) -> str:
    """Append deterministic fixes for classic Geant4 errors found in the output."""
    if not raw_output:
        return raw_output
    hints: list[str] = []
    for sig_a, sig_b, fix in _KNOWN_GEANT4_FIXES:
        if sig_a in raw_output and sig_b in raw_output:
            hints.append(fix)
    if not hints:
        return raw_output
    return raw_output.rstrip() + "\n\n[KNOWN-FIX HINTS]\n" + "\n\n".join(hints) + "\n"


async def run_smoke(project_dir: Path, *, events: int = 5, job_id: str = "agentic") -> dict[str, Any]:
    """Build then run a small smoke simulation end-to-end.

    Returns the COMPLETE raw run output (stdout+stderr, tail-capped) so a
    runtime crash (e.g. ``double free``, segfault) comes through with whatever
    stack/abort text the executable emitted — the model needs this to fix
    memory bugs, just like a developer reading a terminal.
    """
    from agent_core.gates.output_quality import inspect_g4_output_quality
    from agent_core.tools.geant4_runner import Geant4Runner

    runner = Geant4Runner()
    output_dir = project_dir / "smoke_output"
    result = await runner.smoke_test(
        str(project_dir),
        job_id=job_id,
        output_dir=str(output_dir),
        events=max(1, int(events)),
    )
    quality = inspect_g4_output_quality(
        output_dir,
        smoke_result=_smoke_result_for_quality(result),
        expected_events=max(1, int(events)),
    )
    raw = _join_errors(result)
    if quality.errors:
        raw = "\n".join([raw, *quality.errors]).strip()
    # Prefer the full run log when available; fall back to error fields.
    run_log = result.get("run_log") or result.get("log") or ""
    combined = f"{run_log}\n{raw}" if run_log else raw
    return {
        "ok": bool(result.get("success")) and quality.passed,
        "stage": "smoke",
        "output": _known_fix_hints(combined),
        "details": {
            "events_requested": result.get("events_requested"),
            "build_success": result.get("build_success"),
            "run_success": result.get("run_success"),
            "runtime_error_patterns": result.get("runtime_error_patterns"),
            "output_dir": str(output_dir),
            "output_quality": {
                "status": "pass" if quality.passed else "fail",
                "errors": quality.errors,
                "warnings": quality.warnings,
                "metrics": quality.metrics,
            },
        },
    }


def _join_errors(result: dict[str, Any]) -> str:
    parts = []
    for key in ("run_errors", "runtime_error_patterns", "cmake_errors", "build_errors", "errors"):
        value = result.get(key)
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        elif value:
            parts.append(str(value))
    return "\n".join(parts)


def _smoke_result_for_quality(result: dict[str, Any]) -> dict[str, Any]:
    errors = result.get("errors")
    if not errors:
        warnings = result.get("warnings")
        if isinstance(warnings, list):
            errors = "\n".join(str(item) for item in warnings if item)
    return {"success": result.get("success"), "errors": errors or ""}
