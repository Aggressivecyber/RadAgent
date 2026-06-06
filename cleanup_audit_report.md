# RadAgent MVP-1 Cleanup Audit Report

Generated: 2026-06-06 (Updated — Round 2)

## Summary

Full repository cleanup and acceptance hardening for RadAgent MVP-1.
All 8 items from the user directive have been addressed.
**240 tests passing, 0 failures. Ruff clean. Graph compiles.**

---

## Findings Addressed

| ID | Finding | Severity | Status |
|----|---------|----------|--------|
| F-01 | Legacy RAG names (g4rag/tcadrag/spicerag) in tools | HIGH | ✅ Fixed — Geant4RAGTool/TcadTool/SpiceTool |
| F-02 | Legacy env vars (G4RAG_MCP_ENDPOINT etc.) | HIGH | ✅ Fixed — GEANT4_RAG_ENDPOINT/TCAD_RAG_ENDPOINT/SPICE_RAG_ENDPOINT |
| F-03 | Legacy UPPERCASE names in class names | MEDIUM | ✅ Fixed — G4RAGTool→Geant4RAGTool, TCADRAGTool→TcadTool, SPICERAGTool→SpiceTool |
| F-04 | Fan-out retrieve_* nodes still in repo | MEDIUM | ✅ Fixed — marked DEPRECATED, not wired into graph |
| F-05 | write_fix_patch read wrong state key | HIGH | ✅ Fixed — web_context → rag_error_context |
| F-06 | Old decision enum values | MEDIUM | ✅ Fixed — tri-state allow_rag/needs_web/block_no_context |
| F-07 | Gate 9 timestamp only checked 2 of 5 files | HIGH | ✅ Fixed — now checks all 5 required files |
| F-08 | Web supplement had no quality gate | HIGH | ✅ Fixed — requires 2 URLs + 1 official source + keyword match |
| F-09 | No MVP-1 scope guard | HIGH | ✅ Fixed — write_code_patch blocks TCAD/SPICE |
| F-10 | Old job artifacts could be tracked | MEDIUM | ✅ Fixed — .gitignore + tests enforce no tracking |

---

## Verification Results

### 1. No Legacy Names — 11/11 passed

```
test_no_g4rag_in_production_code            PASSED
test_no_tcadrag_in_production_code          PASSED
test_no_spicerag_in_production_code         PASSED
test_no_g4rag_uppercase_in_production       PASSED
test_no_tcadrage_uppercase_in_production    PASSED
test_no_spicerage_uppercase_in_production   PASSED
test_no_allow_with_warning_in_production    PASSED
test_no_bare_allow_in_schemas               PASSED
test_no_bare_block_in_decision_enum         PASSED
test_no_g4rag_endpoint_in_env_example       PASSED
test_no_tcadrage_endpoint_in_env_example    PASSED
```

### 2. No Tracked Job Artifacts — 9/9 passed

```
test_no_tracked_job_directories             PASSED
test_no_tracked_output_csv                  PASSED
test_no_tracked_g4_summary_json             PASSED
test_no_tracked_provenance_json             PASSED
test_no_tracked_run_log                     PASSED
test_no_nested_simulation_workspace         PASSED
test_gitignore_covers_jobs                  PASSED
test_gitignore_covers_nested_workspace      PASSED
test_gitignore_keeps_gitkeep                PASSED
```

### 3. Graph Builder — New Flow

```
prepare_local_rag_workspace
  → parse_user_request → build_task_spec → validate_task_spec
    [3x fail] → generate_report → END
  → build_simulation_ir → validate_simulation_ir
    [3x fail] → generate_report → END
  → route_rag → retrieve_required_context (unified, replaces fan-out)
    → score_rag_sufficiency
      ├─ allow_rag            → plan_simulation
      ├─ needs_web            → retrieve_web_context
      │   → score_combined_context_sufficiency
      │   ├─ allow_with_web_supplement → plan_simulation
      │   └─ block_no_context           → generate_report → END
      └─ block_no_context     → generate_report → END
  → [MVP-1 Scope Guard] write_code_patch
    → review_code_patch → apply_patch (records patch_applied_at)
    → run_gate_checks
      ├─ all pass → parse_simulation_results → validate_data_contract → generate_report
      └─ any fail → classify_failure → (retry / terminate)
```

### 4. Gate 0 — Three Scenarios — 10/10 passed

| Scenario | Input | Expected | Result |
|----------|-------|----------|--------|
| RAG pass | allow_rag, score=0.95 | severity=pass | ✅ PASSED |
| Web supplement | allow_with_web_supplement, score=0.65 | severity=warning | ✅ PASSED |
| Block | block_no_context, score=0.30 | severity=block | ✅ PASSED |
| Web insufficient | block_no_context, web_available=True | severity=block | ✅ PASSED |
| Unknown decision | maybe_perhaps | severity=fail | ✅ PASSED |

### 5. Gate 9 — Timestamp Validation — 5/5 passed

```
test_dev_mode_skips_when_no_g4              PASSED
test_mvp1_fails_when_no_g4                  PASSED
test_passes_when_all_files_present          PASSED
test_fails_when_event_table_empty           PASSED
test_fails_when_provenance_id_mismatch      PASSED
```

Gate 9 validates:
- 5 required files exist (g4_summary.json, edep_3d.csv, dose_3d.csv, event_table.csv, provenance.json)
- event_table.csv ≥ 1 data row
- provenance.json simulation_id == job_id
- g4_summary.json simulation_id == job_id
- **All 5 files** mtime > patch_applied_at (stale file rejection)

### 6. dev_no_geant4_env Mode — 2/2 passed

```
test_dev_mode_allows_skip[asyncio]          PASSED
test_dev_mode_allows_skip[trio]             PASSED
```

### 7. Environment

- **Geant4**: 11.3.2 available at /usr/local/geant4
- **MVP-1 acceptance**: Available — run with `execution_mode=mvp1_acceptance`
- To run acceptance test: `python -m agent_core.main "模拟 10 MeV 质子垂直入射 300 微米硅片"`

### 8. Full Test Suite Summary

```
240 passed, 0 failed in 0.54s
ruff: All checks passed
graph: compiled OK
Geant4: 11.3.2 available
```

---

## Files Changed (This Round)

| File | Change |
|------|--------|
| `agent_core/tools/tcad_rag_tool.py` | TCADRAGTool → TcadTool |
| `agent_core/tools/spice_rag_tool.py` | SPICERAGTool → SpiceTool |
| `agent_core/tools/geant4_rag_tool.py` | GEANT4_RAG_ENDPOINT primary (deprecated compat) |
| `agent_core/config/rag_registry.py` | Env vars updated |
| `agent_core/nodes/retrieve_required_context.py` | Updated class imports |
| `agent_core/nodes/retrieve_g4_context.py` | Marked DEPRECATED |
| `agent_core/nodes/retrieve_tcad_context.py` | Marked DEPRECATED |
| `agent_core/nodes/retrieve_spice_context.py` | Marked DEPRECATED |
| `agent_core/nodes/retrieve_error_context.py` | Updated import |
| `agent_core/nodes/write_code_patch.py` | MVP-1 scope guard |
| `agent_core/nodes/generate_report.py` | MVP-1 scope declaration |
| `agent_core/nodes/run_gate_checks.py` | Gate 9: all 5 files timestamp check |
| `agent_core/nodes/score_combined_context_sufficiency.py` | Web criteria: 2 URL + official + keyword + used_for |
| `tests/unit/test_no_legacy_names.py` | Added UPPERCASE env var scan |
| `tests/unit/test_no_tracked_job_artifacts.py` | Added nested workspace test |
| `tests/unit/test_combined_context_sufficiency.py` | Updated for new Web criteria |
| `README.md` | RAG+Web context sufficiency, MVP-1 候选版, scope guard |
| `cleanup_audit_report.md` | This report |
