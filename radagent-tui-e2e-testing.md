# RadAgent TUI E2E Handoff

## Current Route

The codegen pipeline is now agentic rather than one-shot JSON generation.

Every codegen module agent is a real tool-using agent. Module agents use the
shared `module_workspace/` and receive `read_file`, `write_file`, and
`edit_file` tools unless a module-specific policy disables reads. Integration
repair uses `read_file`, `edit_file`, `write_file`, `build_project`, and
`run_smoke`; `run_bash` is intentionally removed from repair so the model does
not waste turns on grep/cat investigation. The dev toolkit also contains
`run_bash`, but it should stay out of tight repair loops.

Tool loop support was checked: one assistant response can contain multiple
tool calls, and the loop dispatches them all in order. Therefore multi-file
editing should be done as multiple `write_file` or `edit_file` tool calls in
one response when the model already has enough interface context.

## Agent Tool Matrix

All code generation workers below are agents driven through native model
tool-calling, not JSON-only generators.

| Worker | Tools exposed | Notes |
| --- | --- | --- |
| `simulation_core` module agent | `write_file`, `edit_file` | `read_file` is disabled by policy because the IR and prior file summaries should be enough. This avoids investigation turns. |
| `beam_physics` module agent | `read_file`, `write_file`, `edit_file` | Reads upstream/generated headers when needed, then writes owned source/header/macro files. |
| `runtime_app` module agent | `read_file`, `write_file`, `edit_file` for `runtime_cpp`; `write_file`, `edit_file` for `runtime_macros` | The C++ group should batch multiple `write_file` calls after reading upstream headers. The macro group should not spend turns reading files. |
| `agentic_repair` integration repair | `read_file`, `edit_file`, `write_file`, `build_project`, `run_smoke` | Uses raw gcc/build/smoke feedback. `run_bash` is deliberately not exposed here. |
| `DevToolkit` full capability | `read_file`, `edit_file`, `write_file`, `run_bash`, `build_project`, `run_smoke` | This is the common tool library; each agent receives a scoped subset. |

If the desired policy is literally "bash for every module agent", the current
code does not do that. The present route is stricter: module agents only get
file tools, and repair gets build/smoke tools. This keeps agents from burning
turns on shell exploration while preserving multi-file editing through batched
`write_file`/`edit_file` tool calls.

## Speed Changes Already Landed

- Simulation briefing uses one Lite extraction call with no thinking mode.
- G4 modeling requirement capture uses one Lite extraction call, then the
  geometry/physics/material nodes skip work when the draft IR already contains
  the needed components.
- Context coordination after module generation is deterministic; the previous
  nonessential Lite summary call is removed.
- Module codegen runs with no provider thinking mode.
- Simulation core file groups disable `read_file` and use shared prior-file
  summaries to avoid rereading same-module headers.
- Repair uses complete raw `build_project` output and `run_smoke` output,
  including gcc carets and notes, as harness feedback.

## Runtime App Issue To Watch

The observed runtime_app behavior was: second turn wrote only
`OutputManager.hh`; the next turn continued rather than writing all owned C++
files in one batch. This is not a tool dispatcher limitation: the agent loop
handles multiple tool calls from one model response. It is most likely a prompt
or task-organization issue.

Mitigation added for the next run:

- Base module prompt now explicitly says one assistant response can emit
  multiple `write_file`/`edit_file` calls and should batch all owned files when
  enough information is available.
- runtime_app prompt now explicitly treats `runtime_cpp` as one larger wiring
  task and asks the model to batch write OutputManager, actions, main, and
  CMake after reading necessary upstream headers.
- runtime_app remains two larger tasks: one C++ wiring group and one macro
  group. Do not split into many tiny groups unless the next full e2e proves the
  larger-task route cannot complete build/smoke.

## False Success Fix

The TUI service previously advanced phases whenever a subgraph returned a
dict, even when that dict contained `g4_codegen_status=failed`,
`validation_status=failed`, etc. That produced a false `job_finished success`.

The service now treats these as blocking phase failures:

- `task_planning_status` must be `passed`
- `g4_modeling_status` must be `passed`
- `g4_codegen_status` must be `passed`
- `patch_status` must be `applied`
- `validation_status` must be `passed`
- `artifact_status` must be `collected`

If a phase fails, the service records `termination_reason`, emits
`phase_failed`, keeps the current phase index in place, and reports job status
`failed`.

## Final Completion Criterion

Do not accept TUI `job_finished success` alone. Inspect artifacts/events and
confirm all of the following:

1. `g4_codegen_status == passed`
2. `patch_status == applied`
3. `validation_status == passed`
4. `artifact_status == collected`
5. build output has no compile errors
6. smoke run passes
7. output contract files exist and pass quality checks:
   `g4_summary.json`, `provenance.json`, `event_table.csv`, `edep_3d.csv`,
   `dose_3d.csv`

## Next E2E Notes

Start a fresh TUI e2e after this commit and audit the runtime_app tool audit.
Expected improved behavior: after upstream headers are read, runtime_cpp should
write several owned C++ files in the same assistant response instead of one
file per turn.

If runtime_app still writes one file per turn and hits max_turns, check:

- Whether the provider is returning only one `tool_call` despite the prompt.
- Whether `max_tokens=8192` truncates large multi-file write batches.
- Whether tool schema descriptions need to explicitly say multiple tool calls
  in one response are allowed.
- Whether runtime_cpp should increase only `RADAGENT_MODULE_AGENT_MAX_TURNS`
  for this module, before considering more file-group splits.

## Zero-Energy-Deposition Bug (FOUND + FIXED, 2026-06-13)

Auditing the previously-"completed" e2e job `job_cbb4f07a__20260612_072455`
against the 7 completion criteria revealed it was a **false success**: the
TUI reported `completed`, but `logs/failure_bundle.json` showed
`status: failed, phase: gate_validation` with "edep_3d.csv has no non-zero
edep_MeV bins". The generated Geant4 code **built and smoke-ran cleanly but
deposited zero energy** (`total_edep_MeV: 0.0`, event_table.csv all zero).

Root cause is a Geant4 initialization-order bug in the codegen output:

- The generated `DetectorConstruction` created
  `fScoringManager = new ScoringManager()` inside `ConstructSDandField()`.
- Geant4 calls `ActionInitialization::Build()` **BEFORE**
  `ConstructSDandField()`, so `detCon->GetScoringManager()` returned NULL at
  Build() time.
- `EventAction` and `SteppingAction` therefore held a NULL ScoringManager.
  `SensitiveDetector` still recorded (it received the pointer via
  `SetScoringManager` in ConstructSDandField), but the EndOfEvent read path was
  dead — per-event edep was never aggregated. Confirmed by instrument prints:
  `[DBG-REC]` fired 74× with correct edep values, `[DBG-EOE]` fired 0×.

Correct pattern the codegen must emit (validated: rebuild + smoke of the
patched job project gave `total_edep_MeV = 7.2` for 5×1 MeV electrons):

- Create the `ScoringManager` in the `DetectorConstruction` **constructor**
  (guaranteed before Build()), delete it in the destructor. Region
  registration + SD attachment stay in `ConstructSDandField()` where logical
  volumes exist.
- `SensitiveDetector` must record under its **componentId** (set via
  `SetComponentId`), matching `ScoringManager::RegisterRegionScoring`. Never
  use `this->GetName()` as the scoring key.
- Dose units: `dose_Gy = edep_MeV * 1.602176634e-13 / mass_kg`. `* MeV` is NOT
  joules — Geant4's internal energy unit is MeV.
- Register voxel scoring per scored component (IR voxel size in um), or
  edep_3d/dose_3d are empty and the Data Contract gate fails "no non-zero bins".

Fixes landed in this session (output_quality.py + module_context_examples.py
+ a regression test in test_g4_output_quality.py):

- `inspect_g4_output_quality._inspect_event_table` now emits an ERROR when
  every event row is zero-edep, with a root-cause hint. This makes `run_smoke`
  fail (not false-pass) and feeds `agentic_repair` a clear "scoring wiring is
  broken" signal — directly aligned with the raw-feedback principle.
- `module_context_examples.py` simulation_core + runtime_app examples/notes
  now prescribe the correct ScoringManager lifetime, SD-componentId contract,
  dose units, and voxel registration.

Pre-existing (NOT caused by these fixes, verified by revert): 3 failing unit
tests in `test_architecture_invariants.py` and
`test_g4_modeling_gates_codegen_files.py` (gate 18 returns 'warning' not
'fail'; artifact_manifest lacks gate_summary). These are from the prior
session's gate renumbering and remain open.

## Updated Next Steps

1. Commit the staged agentic upgrade + false-success fix + the zero-edep
   fixes above.
2. Start a fresh full TUI e2e. With the false-success fix it can no longer
   report a lying `completed`; with the zero-edep fixes the codegen should now
   produce non-zero edep. Verify the 7 completion criteria, not the TUI badge.
3. If the fresh e2e still shows zero edep, the agentic_repair loop should now
   receive the new "no non-zero edep_MeV rows" feedback and self-correct;
   watch that it converges rather than burning max_turns.
4. Consider fixing the 3 pre-existing gate-invariant test failures as a
   separate follow-up (they weaken confidence in the gate suite but are
   unrelated to physics correctness).

## Validation Outcome (2026-06-13, direct codegen subgraph on job_cbb4f07a IR)

Committed (on top of the agentic upgrade), all addressing concrete observed
failure modes:

- `21ae439` zero-edep: output_quality flags all-zero event_table + examples
  prescribe ScoringManager constructor lifetime / SD-componentId / dose units /
  voxel registration. **The constructor pattern is now RELIABLY adopted by the
  model (confirmed across multiple fresh runs).**
- `f1c594d` repair patch reconstruction excludes `build/` so a stale
  CMakeCache.txt no longer poisons the next runtime_attempt.
- `963dabb` agent-loop opt-in `max_stalls`+`stall_nudge`; agentic_repair uses
  max_stalls=3 so the model can't abandon the task with a text-only answer.
- `4950715` simulation_core examples warn about GeomMgt0002 (region) and
  Geom0003 (overlap) geometry crashes.
- `aacb6a8` agentic repair turn budget 32→48 (the audit showed the agent was
  converging but exhausted 32 turns before clearing compile+runtime).
- `a2178c0` beam_physics examples warn about BeamPhys001 particle-table timing.

Open frontier: each fresh codegen run still trips a DIFFERENT LLM-variance
runtime error before producing edep (run1 overlap, run2 region+signatures,
run3 particle-table). The per-pitfall example guidance above covers all three
observed; each NEW pitfall that surfaces should be added the same way. The
more permanent fix is deterministic scaffolding for the mechanical
PGA/region/geometry setup so the model only writes the physics-specific parts.

