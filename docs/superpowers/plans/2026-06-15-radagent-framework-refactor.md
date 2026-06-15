# RadAgent Framework Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Geant4 template-first codegen framework, safer clarification routing, staged repair feedback, and an LLM debug surface in the workbench.

**Architecture:** New jobs should start from a canonical Geant4 project skeleton with stable interfaces and complete output artifacts. LLMs should fill constrained extension points instead of reinventing core C++ classes; ambiguous or non-Geant4 device requests should become explicit clarification requests. Repair and UI status should expose the exact model/phase/action currently running.

**Tech Stack:** Python backend (`agent_core` LangGraph workflow, pytest), Geant4 generated C++ template files, React/Vite frontend (`web_workbench`, Vitest).

---

### Task 1: Clarification-First Task Planning

**Files:**
- Modify: `agent_core/planning/nodes.py`
- Modify: `agent_core/planning/schemas.py`
- Modify: `agent_core/graph/main_graph.py`
- Modify: `agent_core/reports/nodes.py`
- Test: `tests/unit/test_task_planning_subgraph.py`
- Test: `tests/unit/test_main_graph_subgraph_routing.py`

- [ ] Write failing tests proving a bare MOSFET TID request does not receive default gamma/geometry values and returns `task_planning_status == "needs_user_input"` with concrete missing fields.
- [ ] Change scope detection so MOSFET/TID/device-effect requests prefer `tcad` or clarification unless the query explicitly requests Geant4 energy deposition only.
- [ ] Replace the model-assisted planning prompt with a schema that returns `known`, `assumptions`, `missing`, and `ask_user`; reject model-provided particle defaults when missing hard source data.
- [ ] Persist `clarification_request` in the task spec and propagate `task_spec_errors` / `termination_reason` through the main graph into report output.
- [ ] Run focused pytest for task planning and routing.

### Task 2: Canonical Geant4 Minimal Template

**Files:**
- Create: `agent_core/g4_codegen/template_project.py`
- Modify: `agent_core/g4_codegen/graph_nodes.py`
- Test: `tests/unit/test_g4_template_project.py`
- Test: `tests/unit/test_g4_codegen_subgraph.py`

- [ ] Write failing tests for `create_minimal_geant4_project(project_dir, events=100)` asserting stable file set, CMake, macros, config file, and output contract writer source files exist.
- [ ] Implement the template generator with stable `main.cc`, action classes, detector/source/scoring/output classes, macros, and `config/simulation_config.json` extension point.
- [ ] Update `persist_codegen_output_node` to create/copy the template into `06_patch/geant4_project` before writing or reporting generated output.
- [ ] Ensure template metadata records `template_version`, `extension_points`, and `output_contract` in `05_codegen/template_manifest.json`.
- [ ] Run focused pytest for template and codegen persistence.

### Task 3: Template-Aware Codegen and Repair Boundaries

**Files:**
- Modify: `agent_core/g4_codegen/module_agents/base.py`
- Modify: `agent_core/g4_codegen/module_agents/runtime_app_agent.py`
- Modify: `agent_core/g4_codegen/agentic_repair.py`
- Modify: `agent_core/g4_codegen/global_integration_agent.py`
- Test: `tests/unit/test_module_agent_agentic.py`
- Test: `tests/unit/test_agentic_repair.py`
- Test: `tests/unit/test_global_integration_agent.py`

- [ ] Add tests that module prompts describe template extension points and forbid rewriting core interfaces unless the failure stage explicitly allows it.
- [ ] Add repair stage labels: `compile_repair`, `runtime_repair`, `artifact_contract_repair`, `gate_repair`.
- [ ] Include stage label and allowed file scopes in repair prompts and persisted reports.
- [ ] Expose continuation requests with stage-specific wording and the last blocking diagnostic.
- [ ] Run focused repair/global integration tests.

### Task 4: LLM Debug Workbench Panel

**Files:**
- Modify: `agent_core/app/service.py` or existing API only if frontend cannot derive model calls from events.
- Modify: `agent_core/app/schemas.py` if adding a typed backend view.
- Modify: `web_workbench/src/lib/workbenchPresentation.ts`
- Modify: `web_workbench/src/components/WorkbenchShell.tsx`
- Modify: `web_workbench/src/styles.css`
- Test: `tests/unit/test_web_workbench_api.py` if backend view is added.
- Test: `web_workbench/src/lib/workbenchPresentation.test.ts`
- Test: `web_workbench/src/components/AgentStatusRail.test.tsx` or new focused test.

- [ ] Write failing frontend tests for a visible LLM debug panel listing model calls newest-first with phase, module, model, status, duration, prompt chars, output/error summary, and artifact path.
- [ ] If current `/api/status` or `/api/events` lacks model call fields, add a backend `llm_debug` view derived from `logs/events.jsonl` and `logs/active_model_call.json`.
- [ ] Render the panel as a fixed-height internal scroll area in the workbench, using current cockpit visual style.
- [ ] Include a running-call state from `active_model_call.json` so users can see what the model is doing now.
- [ ] Run focused frontend and backend API tests.

### Task 5: Integration Verification

**Files:**
- No new files expected.

- [ ] Run backend focused tests covering planning, codegen template, repair, app service.
- [ ] Run frontend focused tests and `npm run build`.
- [ ] Inspect current worktree for accidental unrelated edits.
- [ ] Summarize remaining risks and whether Geant4 executable smoke was run or only template unit tests were run.
