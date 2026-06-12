"""Agentic build-fix repair for g4 codegen.

Replaces the old one-shot whole-patch JSON regeneration with a native
tool-calling loop: the model receives a real project directory plus
read/edit/write/bash/build/smoke tools and iterates until the Geant4 project
compiles and the smoke run passes.

Public entry point: :func:`run_agentic_repair`.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent_core.agent_loop import run_agent_loop
from agent_core.dev_tools import DevToolkit
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_CODEGEN

GEANT4_PROJECT_DIRNAME = "geant4_project"

AGENTIC_SYSTEM_PROMPT = """\
You are a Geant4 C++ build-fix engineer. Fix compile/runtime errors with the
fewest possible tool calls — work like a human editing in an IDE: read the
compiler error, fix that exact line, rebuild.

Tools (this is your whole loop — no shell, no grep):
- build_project(): compile the project. The result `output` field contains the
  COMPLETE raw compiler output (gcc errors WITH the `^~~~~` caret lines and
  `note: suggested alternative` hints). Read it like a terminal — it tells you
  exactly which file:line:col is wrong and what the compiler expected. Do NOT
  re-investigate with read_file after a build error unless the error is ambiguous;
  the build output is your ground truth.
- read_file(path): read a file with line numbers. Use it to grab the exact
  current text before editing, or when the build error points somewhere unclear.
- edit_file(path, old_string, new_string): replace ONE unique match. Copy
  old_string verbatim from what read_file/build output showed. If the match
  fails, the tool returns the nearby actual lines — correct old_string from that
  and retry (no need to read_file again).
- write_file(path, content): full file rewrite — only for a file that needs many
  changes at once.
- run_smoke(events?): build + run a tiny simulation. Call ONCE, only after
  build_project succeeds. If smoke passes, you are done.

Geant4 quick fixes (cover ~90% of errors):
- `'G4double' does not name a type` / `was not declared` → the file is missing an
  #include. Add `#include "globals.hh"` (covers G4double/G4int/G4String/G4bool),
  `#include "G4SystemOfUnits.hh"` (units), or the type's specific header, BEFORE
  first use / any anonymous namespace.
- `undefined reference` / `no member named` → the .cc signature doesn't match the
  .hh, or the method isn't qualified as `ClassName::method`. Read the header,
  copy the exact signature.
- includes ALWAYS go at the very top, before constexpr/namespace blocks.

Tight loop (mandatory):
1. build_project (or use the error you were given).
2. read_file the ONE failing file (only if you don't already know the exact text).
3. edit_file the minimal fix.
4. build_project again. Repeat 1-4 per error.
5. When build passes, run_smoke once. Then reply exactly: BUILD AND SMOKE PASSED.

Never call read_file more than once between edits. Never rebuild without having
edited since the last build. Do not rewrite files that already compile.
"""



async def run_agentic_repair(
    proposed_patch: dict[str, Any],
    *,
    job_id: str,
    attempt_index: int,
    runtime_failure_context: dict[str, Any] | None = None,
    max_turns: int | None = None,
    expected_events: int = 5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the agentic build-fix loop over a project assembled from ``proposed_patch``.

    Returns ``(repaired_patch, report)``. ``repaired_patch`` keeps the
    ``proposed_patch`` contract (``changed_files`` etc.) so downstream nodes are
    unchanged. ``report`` carries status, turns, tool audit, and the canonical
    runtime gate result.
    """
    from agent_core.g4_codegen.global_integration_agent import (
        _summarize_runtime_gate_result,
    )
    from agent_core.models.gateway import get_model_gateway
    from agent_core.tools.geant4_runner import Geant4Runner

    attempt_dir = get_job_dir(job_id) / STAGE_CODEGEN / "integration" / f"runtime_attempt_{attempt_index}"
    project_dir = attempt_dir / GEANT4_PROJECT_DIRNAME
    _write_patch_to_project_dir(proposed_patch, project_dir)

    toolkit = DevToolkit(
        project_dir,
        job_id=job_id,
        # Tight loop only: no run_bash. The model fixes errors from the build
        # output directly (like a human in an editor) instead of burning turns
        # on grep/cat investigation.
        tool_names=["read_file", "edit_file", "write_file", "build_project", "run_smoke"],
    )
    gateway = get_model_gateway()

    initial_errors = _extract_initial_errors(runtime_failure_context)
    user_message = _build_user_message(initial_errors, expected_events)

    async def _smoke_passed(_toolkit: DevToolkit, audit: list[dict[str, Any]]) -> bool:
        # Stop as soon as a run_smoke tool call succeeded.
        for entry in reversed(audit):
            if entry.get("name") == "run_smoke":
                return bool(entry.get("ok"))
        return False

    def _diagnosis_nudge(audit: list[dict[str, Any]]) -> str | None:
        """Force an edit when the model stalls on read-only investigation."""
        if len(audit) < 2:
            return None
        recent = audit[-2:]
        if all(a.get("name") == "read_file" for a in recent):
            return (
                "You have read twice without editing. Apply the fix now with "
                "edit_file to the file named in the last build error, then call "
                "build_project to verify."
            )
        return None

    budget = max_turns or int(__import__("os").getenv("RADAGENT_AGENTIC_MAX_TURNS", "32"))

    loop_result = await run_agent_loop(
        gateway=gateway,
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt=AGENTIC_SYSTEM_PROMPT,
        user_message=user_message,
        toolkit=toolkit,
        max_turns=budget,
        max_tokens=8192,
        stop_hook=_smoke_passed,
        nudge_hook=_diagnosis_nudge,
        metadata={
            "job_id": job_id,
            "module_name": "agentic_repair",
            "agentic_attempt": attempt_index,
            "enable_thinking": False,
        },
    )

    # Read back the final project files the model left behind.
    repaired_patch = _reconstruct_patch_from_project(project_dir, proposed_patch)

    # Canonical runtime gate: write the final files to a fresh attempt dir and
    # run the official smoke build. Reuses the tested gate implementation.
    from agent_core.g4_codegen.global_integration_agent import (
        _run_integration_runtime_gate,
    )

    gate = await _run_integration_runtime_gate(
        job_id=job_id,
        proposed_patch=repaired_patch,
        attempt=attempt_index,
        expected_events=expected_events,
    )

    status = "passed" if gate.get("status") == "pass" else "failed"
    report: dict[str, Any] = {
        "status": status,
        "stop_reason": loop_result.stop_reason,
        "n_turns": loop_result.n_turns,
        "tool_calls": len(loop_result.tool_audit),
        "tool_audit": _slim_audit(loop_result.tool_audit),
        "loop_error": loop_result.error,
        "runtime_gate": gate,
        "errors": [] if status == "passed" else _collect_errors(gate, loop_result),
    }
    return repaired_patch, report


# ── helpers ──────────────────────────────────────────────────────────────────


def _write_patch_to_project_dir(patch: dict[str, Any], project_dir: Path) -> None:
    import shutil

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    for entry in patch.get("changed_files", []) or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path", ""))
        content = entry.get("new_content")
        if not path or content is None or path.startswith("/") or ".." in path:
            continue
        target = project_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")


def _reconstruct_patch_from_project(
    project_dir: Path,
    original_patch: dict[str, Any],
) -> dict[str, Any]:
    """Read back every file the model may have edited into a fresh patch."""
    # Never carry build/runtime artifacts between attempts: a stale
    # build/CMakeCache.txt records the PREVIOUS attempt's absolute source
    # path, so cmake refuses to configure the next attempt ("CMakeCache.txt
    # is different than the directory where it was created"). That breaks
    # the repair loop's ability to iterate. Only source files travel onward.
    artifact_segments = {"build", "smoke_output", "CMakeFiles", ".cache"}
    changed: list[dict[str, Any]] = []
    for path in sorted(p for p in project_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(project_dir).as_posix()
        if any(part in artifact_segments for part in rel.split("/")):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Preserve metadata from the original entry when present.
        meta = next(
            (
                e
                for e in original_patch.get("changed_files", [])
                if isinstance(e, dict) and e.get("path") == rel
            ),
            {},
        )
        entry = dict(meta)
        entry.update({"path": rel, "operation": "create_or_replace", "new_content": content})
        changed.append(entry)
    repaired = deepcopy(original_patch)
    repaired["changed_files"] = changed
    return repaired


def _extract_initial_errors(runtime_failure_context: dict[str, Any] | None) -> str:
    if not runtime_failure_context:
        return ""
    parts: list[str] = []
    for key in ("errors", "build_errors", "cmake_errors", "run_errors"):
        value = runtime_failure_context.get(key)
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        elif value:
            parts.append(str(value))
    stderr = runtime_failure_context.get("stderr") or runtime_failure_context.get("build_output")
    if stderr:
        parts.append(str(stderr))
    return "\n".join(parts)[:8000]


def _build_user_message(initial_errors: str, expected_events: int) -> str:
    if initial_errors.strip():
        return (
            "The Geant4 project failed to build/run. Here are the current errors:\n\n"
            f"{initial_errors}\n\n"
            "Read the failing file(s), apply the minimal fix, then call build_project "
            "to verify. Once it compiles, call run_smoke once. Stop after smoke passes."
        )
    return (
        f"Build and verify this Geant4 project. Call build_project; if it fails, fix the "
        f"errors with edit_file and rebuild. When build succeeds, call run_smoke once "
        f"(~{expected_events} events). Stop after smoke passes."
    )


def _slim_audit(audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slimmed: list[dict[str, Any]] = []
    for entry in audit:
        result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
        slimmed.append(
            {
                "turn": entry.get("turn"),
                "name": entry.get("name"),
                "ok": entry.get("ok"),
                "exit_code": result.get("exit_code"),
                "stage": result.get("stage"),
            }
        )
    return slimmed


def _collect_errors(gate: dict[str, Any], loop_result: Any) -> list[str]:
    errors: list[str] = []
    for err in gate.get("errors", []) or []:
        errors.append(str(err)[:500])
    if loop_result.error:
        errors.append(f"agent loop error: {loop_result.error}")
    if loop_result.stop_reason == "max_turns":
        errors.append(f"agent loop exhausted max turns ({loop_result.n_turns})")
    return errors
