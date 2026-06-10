# Review Artifact: Radiation-Hard Silicon Pixel Detector

## Overview
Complex detector model with full sensor stack for Geant4 simulation.
This is a **test fixture** artifact — no actual Geant4 simulation was executed.
Validation scope: fixture model review, not a real Geant4 acceptance run.

## Files
```
latest/
├── README.md
├── artifact_manifest.json
├── review_report.json
└── output/
    ├── g4_model_ir.json          — Full model IR (9 components, 5 materials, 4 scoring)
    ├── gate_results.json          — 20 current gates with detailed checked_items
    ├── component_specs_summary.json
    ├── no_simplification_report.json
    ├── geometry_interface_report.json
    ├── evidence_traceability_report.json
    ├── confirmation_record.json
    ├── confirmed_model_plan.json
    ├── human_confirmation_report.md
    ├── output_manager_contract.json
    ├── model_review_report.md     — Human-readable review
    ├── code_module_plan.json      — Planned codegen modules
    ├── construction_ledger.json   — Model construction ledger
    └── proposed_patch_summary.json
```

## Model
- **Target**: Radiation-hard silicon pixel detector
- **Components**: world, housing, PCB, sensor stack, electrodes, oxide, silicon bulk, sensitive region
- **Source**: 10 MeV proton, vertical incidence
- **Scoring**: edep, dose, 3D dose map, event table

## Validation
- 10/20 gates passed
- 10 non-critical runtime/code-file gates skipped because this is a tracked fixture
- No simplifications applied
- All required components present
- Human confirmation approved
- is_stub: false
