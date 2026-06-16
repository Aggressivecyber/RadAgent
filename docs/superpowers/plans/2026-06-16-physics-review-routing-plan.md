# Physics Review Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop physics review from sending user-confirmation and upstream IR ambiguity issues back to the Geant4 construction agent.

**Architecture:** The physics reviewer must separate code-repairable fixes from user/IR blockers and advisory findings. The codegen graph routes only code-repairable findings back to `geant4_project_agent`; user/IR blockers persist as `needs_user_input` with a structured confirmation request that the existing UI can display.

**Tech Stack:** Python, LangGraph routing helpers, pytest, existing RadAgent workspace artifact paths.

---

### Task 1: Regression Tests

**Files:**
- Modify: `tests/unit/test_g4_codegen_subgraph.py`
- Modify: `tests/unit/test_persist_marks_failed_on_runtime_audit_fail.py`
- Modify: `tests/unit/test_main_graph_subgraph_routing.py`

- [ ] Add tests for physics review normalization and routing.
- [ ] Add tests for codegen persistence writing a structured confirmation request.
- [ ] Add tests that main graph treats `g4_codegen_status=needs_user_input` with a confirmation request as a human-confirmation pause.

### Task 2: Reviewer Contract

**Files:**
- Modify: `agent_core/g4_codegen/physics_quality_reviewer.py`

- [ ] Update the system prompt JSON schema to include `needs_user_input`, `advisory_findings`, and `routing_recommendation`.
- [ ] Normalize old reviewer outputs by moving user-confirmation and G4ModelIR metadata items out of `required_fixes`.
- [ ] Keep runtime/build/artifact issues code-repairable only when they are concrete project-file changes.

### Task 3: Graph Routing And Persistence

**Files:**
- Modify: `agent_core/graph/subgraphs/g4_codegen_graph.py`
- Modify: `agent_core/g4_codegen/graph_nodes.py`
- Modify: `agent_core/graph/main_routes.py`
- Modify: `agent_core/graph/main_graph.py`

- [ ] Route physics review failures back to `geant4_project_agent` only when normalized `routing_recommendation` is `repair_code`.
- [ ] Persist user/IR blockers as `g4_codegen_status=needs_user_input`, `human_confirmation_required=True`, and a concrete confirmation request path.
- [ ] Preserve repair-continuation behavior for exhausted runtime/code repair attempts.
- [ ] Propagate confirmation fields from the codegen subgraph into main graph state.

### Task 4: Verification

**Files:**
- Test: focused unit tests around codegen routing, reviewer normalization, persistence, and main routing.

- [ ] Run `pytest -q tests/unit/test_g4_codegen_subgraph.py tests/unit/test_persist_marks_failed_on_runtime_audit_fail.py tests/unit/test_main_graph_subgraph_routing.py`.
- [ ] Run the narrower prior regression set if focused tests pass.
