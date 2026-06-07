"""Canonical stage name constants for RadAgent workspace.

Import these instead of hardcoding directory names.
"""

# ── Stage identifiers ────────────────────────────────────────────────────
STAGE_INPUT = "00_input"
STAGE_CONTEXT = "01_context"
STAGE_TASK_PLAN = "02_task_plan"
STAGE_MODELING = "03_modeling"
STAGE_HUMAN_CONFIRMATION = "04_human_confirmation"
STAGE_MODEL_IR = "05_model_ir"
STAGE_CODEGEN = "06_codegen"
STAGE_PATCH = "07_patch"
STAGE_GATE_VALIDATION = "08_gate_validation"
STAGE_ARTIFACTS = "09_artifacts"
STAGE_REPORT = "10_report"
STAGE_LOGS = "logs"

# ── Ordered list for directory creation ───────────────────────────────────
ALL_STAGES: tuple[str, ...] = (
    STAGE_INPUT,
    STAGE_CONTEXT,
    STAGE_TASK_PLAN,
    STAGE_MODELING,
    STAGE_HUMAN_CONFIRMATION,
    STAGE_MODEL_IR,
    STAGE_CODEGEN,
    STAGE_PATCH,
    STAGE_GATE_VALIDATION,
    STAGE_ARTIFACTS,
    STAGE_REPORT,
    STAGE_LOGS,
)

# ── Geant4 project subdirectories (under STAGE_PATCH) ────────────────────
GEANT4_SUBDIRS: tuple[str, ...] = (
    "src",
    "include",
    "config",
    "macros",
)

# ── Model IR subdirectories ──────────────────────────────────────────────
MODEL_IR_SUBDIRS: tuple[str, ...] = (
    "component_specs",
)

# ── Human confirmation sub-files ──────────────────────────────────────────
HC_CONFIRMATION_RECORD = "confirmation_record.json"
HC_CONFIRMED_MODEL_PLAN = "confirmed_model_plan.json"
HC_REPORT = "human_confirmation_report.md"
HC_REQUEST_TEMPLATE = "confirmation_request_round_{round}.json"
HC_RESPONSE_TEMPLATE = "confirmation_response_round_{round}.json"
