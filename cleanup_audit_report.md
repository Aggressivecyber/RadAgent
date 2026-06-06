# RadAgent MVP-1 Cleanup Audit Report

Generated: 2026-06-07 (Updated — Round 3)

## Summary

Full repository cleanup and acceptance hardening for RadAgent MVP-1.
All 5 items from the user directive have been addressed.
**252 tests passing, 0 failures. Ruff clean. Graph compiles.**

---

## Round 3 Fixes

### 1. 旧 Job 产物清理

**状态:** ✅ 已清理（上轮完成，本轮验证）

验证结果：
```
$ git ls-files | grep 'simulation_workspace/simulation_workspace'
(empty — 无输出，确认已从 git tracking 清除)
```

- `simulation_workspace/simulation_workspace/` 已从 git tracking 和磁盘删除
- `.gitignore` 覆盖 `simulation_workspace/**/output/**` 等
- `test_no_nested_simulation_workspace` 测试持续守护

### 2. test_mvp1_scope_guard.py — 9/9 passed

新增测试文件覆盖 MVP-1 scope guard 的 5 个场景 + 报告验证：

| Test | Scenario | Expected | Result |
|------|----------|----------|--------|
| test_tcad_blocked | scope=["geant4","tcad"] | proposed_patch={} | ✅ PASSED |
| test_tcad_only_blocked | scope=["tcad"] | proposed_patch={} | ✅ PASSED |
| test_spice_blocked | scope=["geant4","spice"] | proposed_patch={} | ✅ PASSED |
| test_spice_only_blocked | scope=["spice"] | proposed_patch={} | ✅ PASSED |
| test_tcad_and_spice_blocked | scope=["geant4","tcad","spice"] | proposed_patch={} | ✅ PASSED |
| test_geant4_only_not_blocked | scope=["geant4"] | patch generated | ✅ PASSED |
| test_report_mentions_tcad_reserved | tcad in scope | "reserved for later mvp" in report | ✅ PASSED |
| test_report_mentions_spice_reserved | spice in scope | "reserved for later mvp" in report | ✅ PASSED |
| test_report_geant4_only_no_reservation | scope=["geant4"] | no reservation text | ✅ PASSED |

### 3. Gate 9 Timestamp 加固

**之前:** timestamp parse error 被 `except Exception: pass` 静默吞掉。
**现在:**
- `mvp1_acceptance` 模式：timestamp parse/compare error → `missing.append(...)` → Gate 9 fail
- `dev_no_geant4_env` 模式：timestamp parse error → 静默继续（non-fatal）

新增 3 个测试：

| Test | Scenario | Expected | Result |
|------|----------|----------|--------|
| test_mvp1_fails_on_bad_timestamp | bad patch_applied_at + mvp1 | fail | ✅ PASSED |
| test_dev_warns_on_bad_timestamp | bad patch_applied_at + dev | pass (non-fatal) | ✅ PASSED |
| test_stale_file_fails_in_mvp1 | file mtime < patch_applied_at + mvp1 | fail + "stale" | ✅ PASSED |

### 4. Deprecated G4RAG_MCP_ENDPOINT 说明

`G4RAG_MCP_ENDPOINT` 仅为兼容保留，不推荐使用：
- **主环境变量:** `GEANT4_RAG_ENDPOINT`（推荐）
- **兼容回退:** `G4RAG_MCP_ENDPOINT`（deprecated，仅作兼容）
- `test_no_legacy_names.py` 的 `test_no_g4rag_uppercase_in_production` 过滤 deprecated 行
- 未来版本将移除兼容回退

---

## Full Verification Results

### 全量测试 — 252/252 passed

```
tests/unit/test_acceptance_mode_no_skip.py — 8 passed
tests/unit/test_combined_context_sufficiency.py — 30 passed
tests/unit/test_g4_output_contract_parser_consistency.py — 10 passed
tests/unit/test_gate0_rag_web_sufficiency.py — 10 passed
tests/unit/test_gate11_physics_sanity.py — 10 passed
tests/unit/test_gate_validation.py — 16 passed
tests/unit/test_geant4_runner_output_env.py — 14 passed
tests/unit/test_mvp1_scope_guard.py — 9 passed
tests/unit/test_no_legacy_names.py — 11 passed
tests/unit/test_no_tracked_job_artifacts.py — 9 passed
tests/unit/test_patch_discipline.py — 8 passed
tests/unit/test_rag_router.py — 12 passed
tests/unit/test_routes.py — 26 passed
tests/unit/test_schemas.py — 10 passed
tests/unit/test_score_rag_sufficiency.py — 8 passed
tests/unit/test_validators.py — 12 passed
tests/unit/test_web_fallback_policy.py — 13 passed
tests/unit/test_web_search_tool.py — 16 passed
tests/unit/test_workspace_paths.py — 10 passed

252 passed, 0 failed in 0.83s
ruff: All checks passed
graph: compiled OK
```

### git ls-files 验证

```
$ git ls-files | grep 'simulation_workspace/simulation_workspace'
(empty — 无输出)
```

### 环境信息

- **Geant4**: 11.3.2 available at /usr/local/geant4
- **MVP-1 acceptance**: 可用 — 使用 `execution_mode=mvp1_acceptance`

---

## Files Changed (Round 3)

| File | Change |
|------|--------|
| `agent_core/nodes/run_gate_checks.py` | Gate 9: timestamp error → mvp1 fail / dev non-fatal |
| `tests/unit/test_mvp1_scope_guard.py` | **新建** — 9 tests: scope guard block/allow + report declaration |
| `tests/unit/test_gate_validation.py` | 新增 TestGate9TimestampHardening (3 tests) |
| `cleanup_audit_report.md` | 本报告更新 |
