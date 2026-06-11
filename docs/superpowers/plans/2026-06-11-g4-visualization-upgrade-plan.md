# G4 Visualization Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement a blocking Geant4 visualization upgrade: 1000-event batch self-check plus 100-event TUI-managed native Geant4 workbench and human visual verdict.

**Architecture:** Add a small `geant4_workbench` helper for controlled macros and launch metadata, keep `Geant4Runner` as the low-level build/run wrapper, and wire the contract through codegen runtime gates, output audit, service, and TUI commands. The first pass records a blocking visual verdict in service state; persistent database schema changes are not required.

**Tech Stack:** Python 3.11, pytest, Pydantic-style dict contracts, existing RadAgent service/TUI architecture, Geant4 macro/CMake conventions.

---

## File Structure

- Create `agent_core/tools/geant4_workbench.py`: macro generation, self-check macro preparation, workbench launch metadata.
- Modify `agent_core/tools/geant4_runner.py`: add explicit macro event override support and use it from `smoke_test`.
- Modify `agent_core/g4_codegen/global_integration_agent.py`: run 1000-event self-check in runtime gate.
- Modify `agent_core/g4_codegen/runtime_execution_auditor.py`: require expected self-check events when provided by the runtime gate.
- Modify `agent_core/gates/output_quality.py` and `agent_core/gates/base_gates.py`: enforce/report expected event counts and align Gate 6/Gate 9 with 1000-event self-check.
- Modify `agent_core/app/schemas.py` and `agent_core/app/service.py`: add workbench result schema and visual verdict methods.
- Modify `agent_core/tui/commands.py` and `agent_core/tui/app.py`: add `/workbench`, `/visual-approve`, and `/visual-reject`.
- Tests:
  - `tests/unit/test_geant4_runner_output_contract.py`
  - `tests/unit/test_runtime_execution_auditor.py`
  - `tests/unit/test_g4_output_quality.py`
  - `tests/unit/test_g4_output_quality_gates.py`
  - `tests/unit/test_global_integration_agent.py`
  - `tests/unit/test_app_service.py`
  - `tests/unit/test_tui_commands.py`

## Tasks

### Task 1: Controlled Macro Helpers

**Files:**
- Create: `agent_core/tools/geant4_workbench.py`
- Test: `tests/unit/test_geant4_runner_output_contract.py`

- [x] Write failing tests for:
  - replacing `/run/beamOn 10` with `/run/beamOn 1000`;
  - creating visual macros with `/run/initialize`, `/vis/open`, trajectories, hits, and `/run/beamOn 100`;
  - returning a launch environment with `QT_QPA_PLATFORM=xcb` when absent.
- [x] Run the new tests and confirm they fail because `agent_core.tools.geant4_workbench` is missing.
- [x] Implement `prepare_self_check_macro`, `prepare_visual_workbench`, and `visual_workbench_environment`.
- [x] Re-run focused tests and confirm they pass.

### Task 2: Runner Event Override

**Files:**
- Modify: `agent_core/tools/geant4_runner.py`
- Test: `tests/unit/test_geant4_runner_output_contract.py`

- [x] Write a failing async test proving `smoke_test(..., events=1000)` passes a controlled macro containing `/run/beamOn 1000` to `simulate`.
- [x] Run the test and confirm the current runner still uses `macros/run.mac` unchanged.
- [x] Add macro override creation inside `smoke_test` before simulation.
- [x] Re-run focused runner tests.

### Task 3: 1000-Event Runtime Gate And Audit

**Files:**
- Modify: `agent_core/g4_codegen/global_integration_agent.py`
- Modify: `agent_core/g4_codegen/runtime_execution_auditor.py`
- Test: `tests/unit/test_global_integration_agent.py`
- Test: `tests/unit/test_runtime_execution_auditor.py`

- [x] Add failing tests that runtime gate attempts record `expected_events=1000` and that runtime facts reject a 10-event run when expected events is 1000.
- [x] Run tests and confirm failure.
- [x] Change the integration runtime gate to request 1000 events and include expected event count in its result.
- [x] Extend runtime fact collection to compare macro events, summary events, and event table rows against expected events.
- [x] Re-run focused tests.

### Task 4: Output Quality And Base Gates

**Files:**
- Modify: `agent_core/gates/output_quality.py`
- Modify: `agent_core/gates/base_gates.py`
- Test: `tests/unit/test_g4_output_quality.py`
- Test: `tests/unit/test_g4_output_quality_gates.py`

- [x] Add failing tests that `inspect_g4_output_quality(..., expected_events=1000)` rejects summaries/tables with 10 rows and that Gate 6 invokes `smoke_test` with 1000.
- [x] Run tests and confirm failure.
- [x] Add optional expected-event validation to output quality.
- [x] Update base gates to run and report 1000-event self-check consistently.
- [x] Re-run focused gate/output tests.

### Task 5: Service And TUI Workbench

**Files:**
- Modify: `agent_core/app/schemas.py`
- Modify: `agent_core/app/service.py`
- Modify: `agent_core/tui/commands.py`
- Modify: `agent_core/tui/app.py`
- Test: `tests/unit/test_app_service.py`
- Test: `tests/unit/test_tui_commands.py`

- [x] Add failing tests for `prepare_visualization_workbench(events=100)`, `record_visual_verdict`, `/workbench`, `/visual-approve`, and `/visual-reject <notes>`.
- [x] Run tests and confirm failure.
- [x] Add schema/service methods and TUI command parsing/dispatch.
- [x] Re-run focused service/TUI tests.

### Task 6: Verification And Completion Audit

**Files:**
- All modified files.

- [x] Run focused tests:
  - `python -m pytest -q tests/unit/test_geant4_runner_output_contract.py tests/unit/test_runtime_execution_auditor.py tests/unit/test_g4_output_quality.py tests/unit/test_g4_output_quality_gates.py tests/unit/test_global_integration_agent.py tests/unit/test_app_service.py tests/unit/test_tui_commands.py`
- [x] Run static checks:
  - `python -m compileall -q agent_core tests`
  - `python -m ruff check agent_core tests`
- [x] Inspect `git diff` and verify every design requirement has code or test evidence.
