"""Workspace management for RadAgent production pipeline.

This module provides the WorkspaceManager — the single source of truth for
all job directory paths.  Every subgraph node MUST resolve paths through
the manager rather than hardcoding directory names.

Stage numbering convention:

    00_input               — Raw user query + config
    01_context             — RAG / web evidence, context report
    02_task_plan           — Task specification, scope decisions
    03_modeling            — Model readiness, evidence map
    04_human_confirmation  — Confirmation request / response / record
    05_model_ir            — G4 Model IR, component specs, interfaces
    06_codegen             — Proposed patch, code module plan
    07_patch               — Applied patch, generated Geant4 project
    08_gate_validation     — Gate results, validation status
    09_artifacts           — Artifact manifest (pre-collection)
    10_report              — Final report, run summary
    logs                   — Execution logs

Only the ArtifactCollector may write to review_artifacts/.
"""
