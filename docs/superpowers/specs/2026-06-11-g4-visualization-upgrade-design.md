# G4 Visualization Upgrade Design

## Goal

Upgrade RadAgent's generated Geant4 projects so a job is not complete until:

1. The generated project builds, passes ctest, and passes a real 1000-event batch self-check.
2. RadAgent exposes a 100-event native Geant4 visual workbench.
3. The user records a blocking visual verdict approving or rejecting the generated target geometry.

The intended operator experience is: generate code, run automatic self-check, open a TUI-managed native Geant4 workbench, inspect the target/geometry/tracks/hits, then approve or reject.

## Evidence Read

`sim0viz` source was not present under `/home/rylan` or `/home/rylan/RadAgent`. The migration source is therefore:

- Geant4 official B1/B2 examples under `/usr/local/geant4/share/Geant4/examples/basic`.
- Local `sim-viz` skill material under `/home/rylan/.config/opencode/skills/sim-viz`.
- Historical `sim-viz` helper scripts under `/home/rylan/.codex/disabled-skills`.
- Existing RadAgent G4 codegen and runtime paths.

Official B1/B2 establish the launch contract: no command-line macro starts interactive `G4UIExecutive`/`G4VisExecutive`, while a command-line macro runs batch mode through `/control/execute`. B2 also adds GUI menu buttons through `gui.mac` when a GUI session is available.

The local `sim-viz` material adds project experience: require UI/Vis linkage, set `QT_QPA_PLATFORM=xcb` for Wayland-style desktops, disable production output in visual modes, hide world, set `G4VisAttributes` for every logical volume, keep overlap checks enabled, use white background/picking/axis views, and optionally add offscreen screenshot checks later.

## Current State

RadAgent already has most primitives, but they are not yet organized as the requested workflow:

- `agent_core/g4_codegen/global_integration_agent.py` already materializes generated C++ into a runtime attempt and runs `Geant4Runner.smoke_test`, but it currently asks for 10 events.
- `agent_core/tools/geant4_runner.py` accepts an `events` argument, but actual event count is determined by the macro passed to the executable. The runner only records the requested value in materialized summaries.
- `agent_core/g4_codegen/runtime_execution_auditor.py` checks macro/summary/output consistency, but does not require a fixed 1000-event count.
- `agent_core/gates/base_gates.py` labels Gate 9 as 1000 events while Gate 6 currently invokes a 10-event smoke test.
- `agent_core/app/service.py` exposes build and simulation helpers, but has no visualization workbench API or visual verdict state.
- The TUI exposes `/build` and `/simulate`, but not `/workbench`, `/visual-approve`, or `/visual-reject`.

## Design

### Workflow

The new completion workflow is:

1. Codegen assembles a Geant4 project in the codegen runtime attempt sandbox.
2. Global integration runs a 1000-event batch self-check.
3. Runtime audit verifies that the project actually ran, the macro/event summary/event table agree, and the expected event count is 1000.
4. Physics review still runs only after runtime authenticity passes.
5. Patch/gate stages consume the same 1000-event self-check contract.
6. After self-check success, `RadAgentAppService` can prepare a 100-event visual workbench.
7. The TUI command `/workbench [events]` opens or prepares the native Geant4 visual session, defaulting to 100.
8. The job remains visually pending until the user runs `/visual-approve` or `/visual-reject <notes>`.
9. A rejection records concrete notes for follow-up revision.

This is a blocking human gate: final completion cannot be claimed when the visual verdict is missing or rejected.

### Geant4 Macro Contract

Generated projects should contain:

- `macros/run.mac`: batch self-check/production-style macro, no viewer commands, `/run/beamOn 1000` for the self-check path.
- `macros/init_vis.mac`: interactive initialization, default verbosity, `/control/saveHistory`, `/run/initialize`, then `/control/execute macros/vis.mac`.
- `macros/vis.mac`: viewer setup, drawing geometry, trajectories, hits, axes/scale, accumulation, and `/run/beamOn 100`.
- `macros/gui.mac`: optional GUI menu buttons for run, viewer style, refresh/flush, and source presets.
- `macros/physics_list.mac`: unchanged physics-list selection where generated.

The runner must not merely pass `events=1000` to Python metadata. It must execute a macro that contains `/run/beamOn 1000`, or explicitly create a controlled temporary macro with that count before launch.

### Native Workbench Contract

`main.cc` must follow B1/B2:

- Create `G4UIExecutive` before the run manager when no macro argument is provided.
- Set up mandatory detector, physics, and action initialization.
- Initialize `G4VisExecutive` after user initialization wiring and before macro execution.
- With a macro argument, run batch mode via `/control/execute <macro>`.
- Without a macro argument, execute `macros/init_vis.mac`, optionally execute `macros/gui.mac` when `ui->IsGUI()`, and call `SessionStart()`.

The workbench should launch with environment that preserves `DISPLAY` and sets `QT_QPA_PLATFORM=xcb` by default if the variable is absent.

### Visual Style Standard

Each logical volume must have explicit visualization attributes when possible. User-specified component RGB color may override the default color, but the role-derived visibility and alpha policy should remain stable.

Default style rules:

- World: invisible. Debug mode may expose a thin neutral wireframe.
- Assembly/envelope/tracker region/container: wireframe or very low alpha surface, usually cool blue/gray.
- Target/sensitive/scoring volume: force solid, alpha 0.75-0.9, visually prominent.
- Shielding/absorber: translucent solid, alpha 0.35-0.6, neutral gray or blue.
- Thin layer/oxide/dielectric: solid, alpha 0.6-0.75, distinct cyan/teal/yellow-green.
- Metal/electrode: solid, alpha 0.6-0.8, silver/gray.
- Hits: red filled markers.
- Trajectories: smooth, colored by charge or particle, accumulated for exactly 100 visual events.

### New Python Surface

Add `agent_core/tools/geant4_workbench.py` to own visualization/self-check-specific behavior:

- Build a controlled self-check macro from the generated batch macro.
- Build or validate visual macros.
- Generate a launch command and environment for the native workbench.
- Return structured Pydantic-compatible dictionaries for service/TUI use.

`Geant4Runner` remains the low-level configure/build/simulate wrapper. It should gain explicit macro event override support so self-check event count is not metadata-only.

### Service And TUI Surface

`RadAgentAppService` should add:

- `prepare_visualization_workbench(events=100)`: validates generated code/executable, prepares visual macros, emits a `visualization_workbench_ready` event, and returns launch metadata.
- `record_visual_verdict(approved: bool, notes: str = "")`: stores the blocking verdict in service state and emits `visualization_review_approved` or `visualization_review_rejected`.

The TUI should add:

- `/workbench [events]`: default 100, prepares/launches the visual workbench.
- `/visual-approve`: records approval.
- `/visual-reject <notes>`: records rejection with required notes.

The TUI should render visual review state in the existing status/artifact panels without requiring a new frontend architecture.

## Error Handling

- If Geant4 is unavailable, the self-check fails; structure checks do not count as a self-check pass.
- If UI/Vis linkage is absent from CMake or executable dependencies, workbench preparation fails with a concrete message.
- If a 1000-event self-check produces fewer or more event rows than expected, runtime audit fails.
- If visual macro generation cannot find or create `macros/init_vis.mac` and `macros/vis.mac`, workbench preparation fails.
- If the user rejects visual review, the job remains incomplete and records rejection notes for revision.

## Testing

Focused tests should prove:

- Runner macro override rewrites or creates a macro whose `/run/beamOn` count matches the requested self-check event count.
- Runtime audit rejects a 10-event output when 1000 events are required.
- Global integration runtime gate asks for 1000 self-check events.
- Gate labels and execution agree on 1000 events.
- Workbench helper produces `init_vis.mac`, `vis.mac`, and `gui.mac` with B1/B2-style commands.
- Service API returns workbench metadata and records visual verdict state.
- TUI commands parse `/workbench`, `/visual-approve`, and `/visual-reject <notes>`.

## Out Of Scope

- Browser-rendered 3D viewer replacement for Geant4.
- Mandatory offscreen screenshot CI gate in the first pass.
- Full automatic visual correctness classification.
- TCAD or SPICE visualization changes.

Offscreen screenshot checks and smart zoom presets can be added later using the existing `smart_g4_viz.py` experience once the native blocking workbench is stable.
