"""Agentic build-fix repair for g4 codegen.

Replaces the old one-shot whole-patch JSON regeneration with a native
tool-calling loop: the model receives a real project directory plus
read/edit/write/bash/build/smoke tools and iterates until the Geant4 project
compiles and the smoke run passes.

Public entry point: :func:`run_agentic_repair`.
"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent_core.agent_loop import run_agent_loop
from agent_core.dev_tools import DevToolkit
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_CODEGEN

logger = logging.getLogger(__name__)

GEANT4_PROJECT_DIRNAME = "geant4_project"
DEFAULT_AGENTIC_REPAIR_MAX_TURNS = 48
AGENTIC_REPAIR_CONTINUATION_INCREMENT_TURNS = 12
AGENTIC_REPAIR_LESSONS_PATH = (
    Path(STAGE_CODEGEN) / "integration" / "agentic_repair_lessons.json"
)
GEANT4_TYPE_INCLUDE_HINTS = {
    "G4Material": "G4Material.hh",
    "G4VSolid": "G4VSolid.hh",
    "G4ThreeVector": "G4ThreeVector.hh",
    "G4ParticleDefinition": "G4ParticleDefinition.hh",
    "G4ParticleTable": "G4ParticleTable.hh",
    "G4Colour": "G4Colour.hh",
    "G4VisAttributes": "G4VisAttributes.hh",
    "G4RotationMatrix": "G4RotationMatrix.hh",
}

AGENTIC_SYSTEM_PROMPT = """\
You are a Geant4 C++ build-fix engineer. Fix compile/runtime errors with the
fewest possible tool calls — work like a human editing in an IDE: read the
compiler error, fix that exact line, rebuild.

Tools (this is your whole loop — no shell):
- build_project(): compile the project. The result `output` field contains the
  COMPLETE raw compiler output (gcc errors WITH the `^~~~~` caret lines and
  `note: suggested alternative` hints). Read it like a terminal — it tells you
  exactly which file:line:col is wrong and what the compiler expected. Batch
  fixes from the same build output: collect all independent missing includes,
  signature mismatches, and constructor-argument errors first, then edit/write
  the affected files in one response when possible. Do NOT re-investigate with
  read_file after a build error unless the error is ambiguous; the build output
  is your ground truth.
- read_file(path): read a file with line numbers. Use it to grab the exact
  current text before editing, or when the build error points somewhere unclear.
- list_files(glob?): list project source/config files. Use this instead of shell
  when you need to discover the exact generated header/source name.
- search_text(pattern, glob?): search source/config files for a literal symbol,
  constructor, method, or placeholder comment. Use this instead of repeated
  read_file calls when locating API definitions/call sites.
- search_geant4_docs(query): search local Geant4 official docs/examples for API
  signatures, include files, and usage patterns. If an unfamiliar Geant4 class,
  method, macro command, allocator, physics-list API, or visualization API is
  involved and the compiler output does not make the fix obvious, call this
  before guessing.
- search_web(query): search the public web for Geant4/API/compiler context when
  local project files and search_geant4_docs are insufficient. Verify web facts
  against the generated project or official docs before editing.
- edit_file(path, old_string, new_string): replace ONE unique match. Copy
  old_string verbatim from what read_file/build output showed. If the match
  fails, the tool returns the nearby actual lines — correct old_string from that
  and retry once (no need to read_file again). If you see `old_string not found`
  twice for the same file, stop using edit_file for that file and use write_file
  to rewrite the full file from its current content with the intended minimal
  fix applied.
- write_file(path, content): full file rewrite — only for a file that needs many
  changes at once.
- run_smoke(events?): build + run a tiny simulation. Call ONCE, only after
  build_project succeeds. If smoke passes, you are done.

Geant4 quick fixes (cover ~90% of errors):
- `'G4double' does not name a type` / `was not declared` → the file is missing an
  #include. Add `#include "globals.hh"` (covers G4double/G4int/G4String/G4bool),
  `#include "G4SystemOfUnits.hh"` (units), or the type's specific header, BEFORE
  first use / any anonymous namespace.
- `G4ThreeVector does not name a type` → add `#include "G4ThreeVector.hh"` in the
  header/source that declares or uses the field/parameter.
- `G4Circle` incomplete type → add `#include "G4Circle.hh"` in the file that uses
  Hit::Draw / G4Circle.
- `std::vector/std::array/std::map` errors → add the matching standard include
  such as `#include <vector>`.
- `undefined reference` / `no member named` → the .cc signature doesn't match the
  .hh, or the method isn't qualified as `ClassName::method`. Read the header,
  copy the exact signature.
- `no declaration matches 'void OutputManager::WriteSummaryJson()'` while the
  header declares `WriteSummaryJson(G4int)` → remove the stray no-argument .cc
  overload and keep only the parameterized definition aligned with OutputManager.hh.
- `G4ParticleTable::GetParticleTable()` incomplete type → add
  `#include "G4ParticleTable.hh"` to the source that calls it.
- `G4Material has not been declared`, `G4Material*` becomes `int*`, or
  `G4VSolid` incomplete type / `BoundingLimits` errors → add
  `#include "G4Material.hh"` and/or `#include "G4VSolid.hh"` to the declaring
  header/source before changing signatures.
- constructor argument mismatch → read the class header once, then update ALL call
  sites from the same build output to match the exact constructor signature.
- `struct X has no member named Y` or `class X has no member named Y` → do not add
  guessed fields/methods at the call site. Read the declaring header, then either
  use the existing member/API exactly or update the struct/class declaration and
  every initializer/call site in the same edit.
- If a helper call is suggested by the compiler, e.g. `did you mean AddComponent?`,
  prefer the existing helper API and adapt the loop to it. Do not invent aggregate
  helpers such as BuildComponents unless the header already declares them.
- includes ALWAYS go at the very top, before constexpr/namespace blocks.
- Never put `#include` lines inside a function body. If a generated class such as
  SensitiveDetector is used in DetectorConstruction.cc, include its header at the
  top and align all constructor calls with the header signature in one edit.
- `G4THREADLOCAL` is not a Geant4 11 macro. Use `G4ThreadLocal` with
  `#include "tls.hh"` for allocator globals, or avoid fragile allocator globals
  entirely when a simple pattern is enough.
- `G4PhysListFactory::GetReferencePhysList` returns a modular physics-list pointer
  in common Geant4 versions. Include the concrete Geant4 physics-list header before
  casting/assigning, and do not guess pointer conversions from forward declarations.
- Event/track ids for particle_tracks.json and energy_deposits.json must come from
  G4Event/G4Track/G4Step data. Do not leave placeholder event_id=0 or track_id=0
  comments in generated runtime code.
- `core dumped`, GeomVol1002/Geom0003, or overlap warnings → inspect geometry
  containment first. A shield/veto/shell that fully contains another solid must
  not be placed as a same-level overlapping solid; use a shell/boolean subtraction
  or mother-daughter containment.
- Missing output contract files after smoke → fix OutputManager/RunAction/EventAction
  so event_table.csv, edep_3d.csv, dose_3d.csv, g4_summary.json, provenance.json,
  geometry_view.json, particle_tracks.json, and energy_deposits.json are written
  even when no hits occur.
- `fGeometryComponents was not declared in this scope` in
  OutputManager::WriteGeometryViewJson → do not keep a fallback that references
  fGeometryComponents unless OutputManager.hh declares that member. Either add
  the member and populate it, or rewrite geometry_view.json from fixed IR-derived
  component JSON. The browser workbench needs non-empty geometry_view.json.
- If event rows are derived from AddEnergyDepositPoint/energy_deposits, both
  event_table.csv and g4_summary.json must use the same derived event rows.
  Do not fix only one of them, and do not leave a helper variable visible in
  WriteProvenanceJson or unrelated OutputManager functions.
- `std::length_error` / `max_size` during smoke → check voxel/bin dimensions before
  allocating vectors; cap bins per axis and avoid 10 um defaults for cm-scale
  detector volumes.

Tight loop (mandatory):
1. build_project (or use the error you were given).
2. Group all independent errors from the same build output by root cause and file.
3. If the failing symbol/call site location is unclear, use search_text or
   list_files once; then read_file only the exact file(s) you will edit.
4. edit_file/write_file the minimal batched fix.
5. build_project again. Repeat 1-5 per error batch.
6. When build passes, run_smoke once. Then reply exactly: BUILD AND SMOKE PASSED.

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

    toolkit = _Geant4RepairToolkit(
        project_dir,
        job_id=job_id,
        # Tight loop only: no run_bash. Safe source search is allowed because
        # generated Geant4 projects often need symbol/call-site discovery.
        tool_names=[
            "list_files",
            "search_text",
            "search_geant4_docs",
            "search_web",
            "read_file",
            "edit_file",
            "write_file",
            "build_project",
            "run_smoke",
        ],
    )
    gateway = get_model_gateway()

    initial_errors = _extract_initial_errors(runtime_failure_context)
    previous_lessons = _load_repair_lessons(job_id)
    user_message = _build_user_message(
        initial_errors,
        expected_events,
        previous_lessons=previous_lessons,
    )

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

    budget = max_turns or int(
        __import__("os").getenv(
            "RADAGENT_AGENTIC_MAX_TURNS",
            str(DEFAULT_AGENTIC_REPAIR_MAX_TURNS),
        )
    )
    history_chars = _optional_positive_int(
        __import__("os").getenv("RADAGENT_AGENTIC_HISTORY_CHARS")
    )

    loop_result = await run_agent_loop(
        gateway=gateway,
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt=AGENTIC_SYSTEM_PROMPT,
        user_message=user_message,
        toolkit=toolkit,
        max_turns=budget,
        max_tokens=16384,
        stop_hook=_smoke_passed,
        nudge_hook=_diagnosis_nudge,
        metadata={
            "job_id": job_id,
            "module_name": "agentic_repair",
            "agentic_attempt": attempt_index,
            "enable_thinking": True,
        },
        max_stalls=8,
        repeated_tool_result_limit=3,
        max_history_chars=history_chars,
        preserve_recent_tool_messages=2,
        stall_nudge=(
            "You stopped without calling a tool. The simulation still does not "
            "pass. Diagnose the current error from the latest build_project or "
            "run_smoke output, use search_geant4_docs if an unfamiliar Geant4 "
            "API or signature is involved, use search_web when local docs are "
            "insufficient, then apply the smallest edit_file or "
            "write_file change and verify with build_project. If the build "
            "passes, call run_smoke once."
        ),
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
    failure_lessons = _build_failure_lessons(
        gate=gate,
        loop_stop_reason=loop_result.stop_reason,
        loop_turns=loop_result.n_turns,
        loop_error=loop_result.error,
    )
    if failure_lessons:
        _persist_repair_lessons(job_id, failure_lessons)
    report: dict[str, Any] = {
        "status": status,
        "stop_reason": loop_result.stop_reason,
        "n_turns": loop_result.n_turns,
        "tool_calls": len(loop_result.tool_audit),
        "tool_audit": _slim_audit(loop_result.tool_audit),
        "loop_error": loop_result.error,
        "runtime_gate": gate,
        "failure_lessons": failure_lessons,
        "errors": [] if status == "passed" else _collect_errors(gate, loop_result),
    }
    continuation_request = _build_continuation_request(loop_result, gate)
    if continuation_request:
        report["continuation_request"] = continuation_request
    return repaired_patch, report


class _Geant4RepairToolkit(DevToolkit):
    """DevToolkit variant that applies deterministic Geant4 source hardening."""

    async def _invoke(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await super()._invoke(name, args)
        if name not in {"edit_file", "write_file"} or not result.get("ok"):
            return result
        path = str(args.get("path") or "")
        if _postprocess_project_file(self.project_dir, path):
            result = dict(result)
            result["postprocessed"] = True
        return result

    def _invoke_sync_for_test(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = super()._invoke_sync_for_test(name, args)
        if name not in {"edit_file", "write_file"} or not result.get("ok"):
            return result
        path = str(args.get("path") or "")
        if _postprocess_project_file(self.project_dir, path):
            result = dict(result)
            result["postprocessed"] = True
        return result


# ── helpers ──────────────────────────────────────────────────────────────────


def _postprocess_project_file(project_dir: Path, path: str) -> bool:
    from agent_core.dev_tools.security import PathEscapeError, resolve_within
    from agent_core.g4_codegen.module_agents.base import _postprocess_generated_module_content

    if not path.endswith((".cc", ".cpp", ".cxx", ".hh", ".hpp", ".h", ".mac")):
        return False
    try:
        target = resolve_within(project_dir, path)
    except PathEscapeError:
        return False
    if not target.is_file():
        return False
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    updated = _postprocess_generated_module_content(path, content)
    if updated == content:
        return False
    target.write_text(updated, encoding="utf-8")
    return True


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
    from agent_core.g4_codegen.module_agents.base import _postprocess_generated_module_content
    from agent_core.validators.file_permission_validator import FilePermissionValidator

    # Never carry build/runtime artifacts between attempts: a stale
    # build/CMakeCache.txt records the PREVIOUS attempt's absolute source
    # path, so cmake refuses to configure the next attempt ("CMakeCache.txt
    # is different than the directory where it was created"). That breaks
    # the repair loop's ability to iterate. Only source files travel onward.
    artifact_segments = {"build", "smoke_output", "CMakeFiles", ".cache"}
    permission_validator = FilePermissionValidator()
    changed: list[dict[str, Any]] = []
    for path in sorted(p for p in project_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(project_dir).as_posix()
        if any(part in artifact_segments for part in rel.split("/")):
            continue
        if not permission_validator.can_auto_apply(rel):
            logger.warning(
                "Skipping generated project file outside auto-apply policy: %s",
                rel,
            )
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        content = _postprocess_generated_module_content(rel, content)
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
        _ensure_reconstructed_entry_metadata(entry, rel)
        changed.append(entry)
    repaired = deepcopy(original_patch)
    repaired["changed_files"] = changed
    return repaired


def _ensure_reconstructed_entry_metadata(entry: dict[str, Any], path: str) -> None:
    if not entry.get("zone"):
        entry["zone"] = _infer_patch_zone(path)
    if not entry.get("generated_by"):
        entry["generated_by"] = "agentic_repair"
    if not entry.get("module_name"):
        entry["module_name"] = _infer_module_name(path)


def _infer_patch_zone(path: str) -> str:
    if path == "main.cc" or path == "CMakeLists.txt":
        return "application"
    if path.startswith("macros/"):
        return "runtime_macro"
    if path.startswith("include/"):
        return "header"
    if path.startswith("src/"):
        return "source"
    return "generated_project"


def _infer_module_name(path: str) -> str:
    if path == "main.cc" or path == "CMakeLists.txt" or path.startswith("macros/"):
        return "runtime_app"
    name = Path(path).stem.lower()
    if any(token in name for token in ("generator", "physics")):
        return "beam_physics"
    if any(token in name for token in ("output", "action", "run", "event", "stepping")):
        return "runtime_app"
    return "simulation_core"


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
    raw = "\n".join(parts)
    brief = _structured_repair_brief(raw)
    if brief:
        return f"{brief}\n\nRaw failure context:\n{raw}"
    return raw


def _structured_repair_brief(raw_errors: str) -> str:
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    pattern = re.compile(
        r"(?P<path>(?:[A-Za-z]:)?[^:\n]*?(?:src|include|macros)/[^:\n]+):"
        r"(?P<line>\d+)(?::(?P<col>\d+))?:\s*"
        r"(?P<kind>fatal error|error|warning):\s*(?P<message>[^\n]+)"
    )
    for match in pattern.finditer(raw_errors):
        path = _project_relative_error_path(match.group("path"))
        line = match.group("line")
        message = match.group("message").strip()
        key = (path, line, message)
        if key in seen:
            continue
        seen.add(key)
        items.append({"path": path, "line": line, "message": message})
        if len(items) >= 12:
            break
    if not items:
        return ""

    by_path: dict[str, list[dict[str, str]]] = {}
    for item in items:
        by_path.setdefault(item["path"], []).append(item)

    lines = [
        "Structured repair brief:",
        "- Fix all listed errors from one build output before rebuilding.",
    ]
    for path, path_items in by_path.items():
        lines.append(f"- {path}:")
        for item in path_items[:6]:
            lines.append(f"  line {item['line']}: {item['message']}")
    return "\n".join(lines)


def _project_relative_error_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    marker = "/geant4_project/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    for prefix in ("src/", "include/", "macros/"):
        index = normalized.find(prefix)
        if index >= 0:
            return normalized[index:]
    return normalized


def _build_user_message(
    initial_errors: str,
    expected_events: int,
    *,
    previous_lessons: list[dict[str, Any]] | None = None,
) -> str:
    lessons_text = _format_previous_repair_lessons(previous_lessons or [])
    if initial_errors.strip():
        return (
            "The Geant4 project failed to build/run. Here are the current errors:\n\n"
            f"{initial_errors}\n\n"
            f"{lessons_text}"
            "Read the failing file(s), apply the minimal fix, then call build_project "
            "to verify. Once it compiles, call run_smoke once. Stop after smoke passes."
        )
    return (
        f"Build and verify this Geant4 project. Call build_project; if it fails, fix the "
        f"errors with edit_file and rebuild. When build succeeds, call run_smoke once "
        f"(~{expected_events} events). Stop after smoke passes.\n\n"
        f"{lessons_text}".rstrip()
    )


def _format_previous_repair_lessons(lessons: list[dict[str, Any]]) -> str:
    if not lessons:
        return ""
    lines = ["Previous repair lessons for this job:"]
    for lesson in lessons[:8]:
        lesson_id = str(lesson.get("id") or "")
        instruction = str(lesson.get("prompt_instruction") or lesson.get("title") or "")
        if not lesson_id or not instruction:
            continue
        lines.append(f"- {lesson_id}: {instruction}")
    return "\n".join(lines).strip() + "\n\n" if len(lines) > 1 else ""


def _load_repair_lessons(job_id: str) -> list[dict[str, Any]]:
    path = get_job_dir(job_id) / AGENTIC_REPAIR_LESSONS_PATH
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    lessons = data.get("lessons") if isinstance(data, dict) else []
    if not isinstance(lessons, list):
        return []
    return [
        lesson
        for lesson in lessons
        if isinstance(lesson, dict) and lesson.get("id") and lesson.get("prompt_instruction")
    ][:12]


def _persist_repair_lessons(job_id: str, new_lessons: list[dict[str, Any]]) -> Path:
    path = get_job_dir(job_id) / AGENTIC_REPAIR_LESSONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_repair_lessons(job_id)
    merged = _merge_repair_lessons(existing, new_lessons)
    payload = {
        "schema_version": "agentic_repair_lessons_v1",
        "job_id": job_id,
        "lessons": merged[:20],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _merge_repair_lessons(
    existing: list[dict[str, Any]],
    new_lessons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for lesson in existing + new_lessons:
        lesson_id = str(lesson.get("id") or "")
        if not lesson_id:
            continue
        current = by_id.get(lesson_id, {})
        merged = {**current, **lesson}
        merged["count"] = int(current.get("count") or 0) + int(lesson.get("count") or 1)
        by_id[lesson_id] = merged
    return sorted(
        by_id.values(),
        key=lambda item: (-int(item.get("count") or 0), str(item.get("id") or "")),
    )


def _build_failure_lessons(
    *,
    gate: dict[str, Any],
    loop_stop_reason: str,
    loop_turns: int,
    loop_error: str | None,
) -> list[dict[str, Any]]:
    text = _failure_lesson_text(gate, loop_stop_reason, loop_error)
    lessons: list[dict[str, Any]] = []
    lowered = text.lower()
    missing_type_instruction = _missing_geant4_type_instruction(text)
    if missing_type_instruction:
        lessons.append(
            _lesson(
                "geant4_missing_type_include",
                "Add Geant4 type headers before changing signatures",
                missing_type_instruction,
                evidence="Geant4 type has not been declared",
            )
        )
    if "no declaration matches" in lowered or "does not match any" in lowered:
        lessons.append(
            _lesson(
                "signature_mismatch",
                "Align source definitions with header declarations",
                (
                    "For no-declaration-matches errors, read the owning header and "
                    "copy the exact method signature into the .cc definition. Fix all "
                    "call sites from the same build output before rebuilding."
                ),
                evidence="no declaration matches",
            )
        )
    if "fgeometrycomponents" in lowered and "not declared" in lowered:
        lessons.append(
            _lesson(
                "geometry_view_phantom_member",
                "Do not reference undeclared geometry members",
                (
                    "Before writing WriteGeometryViewJson, check OutputManager.hh. "
                    "If fGeometryComponents is absent, generate non-empty "
                    "geometry_view.json from IR-derived component JSON instead of "
                    "referencing a phantom member."
                ),
                evidence="fGeometryComponents not declared",
            )
        )
    if "missing output contract files" in lowered:
        lessons.append(
            _lesson(
                "missing_output_contract",
                "Write all required Geant4 output artifacts",
                (
                    "Treat event_table.csv, edep_3d.csv, dose_3d.csv, g4_summary.json, "
                    "provenance.json, geometry_view.json, particle_tracks.json, and "
                    "energy_deposits.json as a single output contract. Fix the writer "
                    "that owns all missing artifacts before rerunning smoke."
                ),
                evidence="Missing output contract files",
            )
        )
    if "old_string not found" in lowered or "repeated failing tool result" in lowered:
        lessons.append(
            _lesson(
                "exact_edit_failed",
                "Use write_file after repeated exact-edit failures",
                (
                    "If edit_file reports old_string not found for the same file, do not "
                    "spend more turns trying variants. Read the current file once if needed, "
                    "then use write_file to rewrite the full same file with the intended "
                    "minimal fix applied."
                ),
                evidence="edit_file old_string not found",
            )
        )
    if "no member named" in lowered:
        lessons.append(
            _lesson(
                "declared_interface_only",
                "Use declared struct fields and helper methods only",
                (
                    "For 'no member named' compile errors, read the owning header "
                    "and align every initializer/call site with the declared API. "
                    "Do not keep guessed fields such as posX/rotX or aggregate "
                    "helpers such as BuildComponents unless they are declared."
                ),
                evidence="no member named",
            )
        )
    if (
        "geometry_view.json" in lowered
        or "particle_tracks.json" in lowered
        or "energy_deposits.json" in lowered
    ):
        lessons.append(
            _lesson(
                "visual_workbench_artifact",
                "Keep the browser workbench artifacts non-empty",
                (
                    "The front-end 3D workbench requires non-empty geometry_view.json, "
                    "true step-derived particle_tracks.json, and edep>0 "
                    "energy_deposits.json. Do not create placeholder or empty files."
                ),
                evidence="visual artifact contract mentioned",
            )
        )
    if "event_table.csv" in lowered or "g4_summary.json" in lowered:
        lessons.append(
            _lesson(
                "event_summary_contract",
                "Use one source of truth for event rows and summary",
                (
                    "When event rows are derived from energy deposit points, use the "
                    "same derived rows for event_table.csv and g4_summary.json so "
                    "event counts and total energy agree."
                ),
                evidence="event table or summary contract mentioned",
            )
        )
    if "std::length_error" in lowered or "max_size" in lowered:
        lessons.append(
            _lesson(
                "voxel_grid_allocation",
                "Cap voxel grid allocation",
                (
                    "Before allocating voxel vectors, cap bins per axis and avoid "
                    "10 um defaults for cm-scale detectors."
                ),
                evidence="length_error/max_size",
            )
        )
    if "geomvol1002" in lowered or "geom0003" in lowered or "overlap" in lowered:
        lessons.append(
            _lesson(
                "geometry_overlap",
                "Model containing volumes as shells or parents",
                (
                    "A shield/shell that fully contains another solid must not be "
                    "placed as a same-level overlapping solid; use shell subtraction "
                    "or mother-daughter containment."
                ),
                evidence="geometry overlap",
            )
        )
    if loop_stop_reason == "max_turns":
        lessons.append(
            _lesson(
                "agent_loop_max_turns",
                "Batch fixes before rebuilding",
                (
                    f"The last repair exhausted {loop_turns} turns. Group independent "
                    "compiler errors from one build output, edit all affected files in "
                    "one batch, then rebuild."
                ),
                evidence="agent loop max_turns",
            )
        )
    return _dedupe_lessons(lessons)


def _missing_geant4_type_instruction(text: str) -> str:
    lowered = text.lower()
    if "has not been declared" not in lowered:
        return ""
    headers = [
        header
        for type_name, header in GEANT4_TYPE_INCLUDE_HINTS.items()
        if type_name.lower() in lowered
    ]
    if not headers:
        return ""
    header_list = ", ".join(sorted(set(headers)))
    return (
        f"Add the missing Geant4 header(s) {header_list} to the declaring header "
        "or source before changing method signatures. Forward declarations are not "
        "enough for pointer parameters when the generated .hh/.cc signatures must "
        "match exactly."
    )


def _lesson(
    lesson_id: str,
    title: str,
    prompt_instruction: str,
    *,
    evidence: str,
) -> dict[str, Any]:
    return {
        "id": lesson_id,
        "title": title,
        "prompt_instruction": prompt_instruction,
        "evidence": evidence,
        "count": 1,
    }


def _dedupe_lessons(lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for lesson in lessons:
        lesson_id = str(lesson.get("id") or "")
        if not lesson_id or lesson_id in seen:
            continue
        seen.add(lesson_id)
        unique.append(lesson)
    return unique


def _failure_lesson_text(
    gate: dict[str, Any],
    loop_stop_reason: str,
    loop_error: str | None,
) -> str:
    parts = [
        json.dumps(gate.get("errors", []), ensure_ascii=False, default=str),
        json.dumps(gate.get("warnings", []), ensure_ascii=False, default=str),
        json.dumps(gate.get("missing_outputs", []), ensure_ascii=False, default=str),
        json.dumps(gate.get("output_quality", {}), ensure_ascii=False, default=str),
        str(loop_stop_reason or ""),
        str(loop_error or ""),
    ]
    return "\n".join(part for part in parts if part)


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


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _collect_errors(gate: dict[str, Any], loop_result: Any) -> list[str]:
    errors: list[str] = []
    for err in gate.get("errors", []) or []:
        errors.append(str(err)[:500])
    if loop_result.error:
        errors.append(f"agent loop error: {loop_result.error}")
    if loop_result.stop_reason == "max_turns":
        errors.append(f"agent loop exhausted max turns ({loop_result.n_turns})")
    return errors


def _build_continuation_request(loop_result: Any, gate: dict[str, Any]) -> dict[str, Any]:
    if loop_result.stop_reason != "max_turns" or gate.get("status") == "pass":
        return {}
    current_turns = int(getattr(loop_result, "n_turns", 0) or 0)
    next_turns = current_turns + AGENTIC_REPAIR_CONTINUATION_INCREMENT_TURNS
    return {
        "status": "pending",
        "reason": "agent_loop_max_turns",
        "current_turns": current_turns,
        "increment_turns": AGENTIC_REPAIR_CONTINUATION_INCREMENT_TURNS,
        "requested_total_turns": next_turns,
        "message": (
            f"修复 Agent 已耗尽 {current_turns} 轮但仍未通过运行门禁，"
            f"是否增加 {AGENTIC_REPAIR_CONTINUATION_INCREMENT_TURNS} 轮继续修复？"
        ),
    }
