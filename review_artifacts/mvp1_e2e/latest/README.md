# MVP-1 E2E Review Artifact

This directory contains lightweight review artifacts from the RadAgent MVP-1 E2E test run.

## Files

| File | Description |
|------|-------------|
| `review_report.json` | Top-level summary: mode, verification status, gate results, test counts |
| `review_artifact_manifest.json` | Checksums of all files in this bundle |
| `output/user_query.md` | Original natural language request |
| `output/task_spec.json` | Parsed task specification |
| `output/simulation_ir.json` | Simulation intermediate representation |
| `output/proposed_patch_summary.json` | Code patch metadata (contents truncated to 200 chars) |
| `output/gate_results.json` | All 12 gate check results |
| `output/final_report.md` | Full pipeline report with MVP-1 verification status |
| `output/edep_3d_head.csv` | First 5 rows of energy deposition data |
| `output/dose_3d_head.csv` | First 5 rows of dose distribution data |
| `output/event_table_head.csv` | First 5 rows of event table |
| `output/g4_summary.json` | Geant4 simulation summary |
| `output/provenance.json` | Simulation provenance metadata |
| `output/checksums.json` | SHA256 checksums of output files |
| `output/collection_manifest.json` | List of collected artifacts with sizes |

## Verification Status

The `review_report.json` contains the `verification_status` field:

- **MVP-1 VERIFIED**: All gates passed in acceptance mode with Geant4
- **NOT VERIFIED**: Dev mode run (Geant4 unavailable), cannot verify
- **MVP-1 FAILED**: Acceptance mode run with gate failures

## Regenerating

```bash
# Dev mode (no Geant4 required)
python scripts/run_mvp1_e2e.py --mode dev
python scripts/collect_mvp1_artifacts.py \
    --job-dir simulation_workspace/jobs/<job_id> \
    --output-dir review_artifacts/mvp1_e2e/latest/output
python scripts/make_review_artifact.py \
    --mode dev \
    --run-results review_artifacts/mvp1_e2e/latest/e2e_results.json \
    --artifacts-dir review_artifacts/mvp1_e2e/latest/output \
    --output-dir review_artifacts/mvp1_e2e/latest

# Acceptance mode (requires Geant4 + OPENAI_API_KEY)
python scripts/run_mvp1_e2e.py --mode acceptance
# ... same collection steps with --mode acceptance
```

## Constraints

- No file in this directory exceeds 100KB
- No HDF5, ROOT, or RAW binary files are included
- CSV files are truncated to header + 5 data rows
- Code content in proposed_patch_summary.json is truncated to 200 characters
