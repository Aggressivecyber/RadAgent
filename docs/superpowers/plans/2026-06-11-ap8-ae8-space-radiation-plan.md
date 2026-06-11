# AP8/AE8 Space Radiation Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local AP8/AE8 trapped-radiation data support and expose it to RadAgent briefing/copilot and Geant4 source configuration.

**Architecture:** Data download and manifests live in `knowledge_base.space_radiation`; simulation-facing request parsing, orbit sampling, true AP8/AE8 flux evaluation, and Geant4 source package generation live in `agent_core.space_radiation`. Existing briefing/chat prompts and `SourceSpec.energy.spectrum_file` are reused rather than adding a new codegen path.

**Tech Stack:** Python 3.11, Pydantic models, pytest, `aep8`, `astropy`, `skyfield`, `sgp4`, urllib/request filesystem download helpers, existing RadAgent briefing and G4 modeling schemas.

---

### Task 1: AP8/AE8 Data Manifest

**Files:**
- Create: `knowledge_base/space_radiation/__init__.py`
- Create: `knowledge_base/space_radiation/paths.py`
- Create: `knowledge_base/space_radiation/ap8ae8.py`
- Test: `tests/unit/test_ap8ae8_data_manifest.py`

- [ ] Write failing tests for manifest creation from local sample files.
- [ ] Run `pytest tests/unit/test_ap8ae8_data_manifest.py -q` and confirm import failures.
- [ ] Implement data path constants, required file metadata, hash calculation, manifest read/write, and optional download from NASA raw URLs.
- [ ] Re-run the focused test and confirm pass.

### Task 2: Space Radiation Source Provider

**Files:**
- Create: `agent_core/space_radiation/__init__.py`
- Create: `agent_core/space_radiation/ap8ae8_provider.py`
- Test: `tests/unit/test_space_radiation_provider.py`

- [ ] Write failing tests for request parsing, missing fields, model selection, geodetic orbit samples, TLE sampling, true AP8/AE8 spectrum generation, and task particle mapping.
- [ ] Run `pytest tests/unit/test_space_radiation_provider.py -q` and confirm failures.
- [ ] Implement `OrbitRadiationRequest`, `OrbitRadiationSourcePackage`, model selection, validation, real AP8/AE8 spectrum CSV generation, TLE sampling, and `to_task_particle()`.
- [ ] Re-run the focused test and confirm pass.

### Task 3: Briefing And Copilot Binding

**Files:**
- Modify: `agent_core/chat/briefing.py`
- Modify: `agent_core/chat/prompts.py`
- Modify: `agent_core/chat/agent.py`
- Test: `tests/unit/test_simulation_briefing.py`
- Test: `tests/unit/test_chat_agent_context.py`

- [ ] Add failing tests that briefing prompts include required orbit-radiation fields and AP8/AE8 limitations.
- [ ] Add failing tests that chat prompt assembly injects local AP8/AE8 context for orbit-radiation wording.
- [ ] Run the two focused tests and confirm failures.
- [ ] Update prompts and prompt assembly with the local space-radiation context.
- [ ] Re-run focused tests and confirm pass.

### Task 4: SourceSpec Compatibility

**Files:**
- Modify: `agent_core/g4_modeling/nodes/source_definition_node.py`
- Test: `tests/unit/test_space_radiation_provider.py`

- [ ] Add a failing test that an AP8/AE8 task particle preserves `source_evidence` into `SourceSpec`.
- [ ] Run the focused test and confirm failure.
- [ ] Update source construction to pass through caller-provided `source_evidence`.
- [ ] Re-run the focused test and confirm pass.

### Task 5: Verification

**Files:**
- All changed files.

- [ ] Run `pytest tests/unit/test_ap8ae8_data_manifest.py tests/unit/test_space_radiation_provider.py tests/unit/test_simulation_briefing.py tests/unit/test_chat_agent_context.py -q`.
- [ ] Run `ruff check agent_core/space_radiation knowledge_base/space_radiation agent_core/chat/briefing.py agent_core/chat/prompts.py agent_core/chat/agent.py agent_core/g4_modeling/nodes/source_definition_node.py tests/unit/test_ap8ae8_data_manifest.py tests/unit/test_space_radiation_provider.py tests/unit/test_simulation_briefing.py tests/unit/test_chat_agent_context.py`.
- [ ] If the AP8/AE8 data is not present locally, run the downloader command or report the network/source failure clearly.
