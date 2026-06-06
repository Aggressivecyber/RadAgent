"""Patch format and content validator."""

import re
from typing import Any

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

PATCH_REQUIRED_FIELDS = {
    "patch_id", "job_id", "description", "change_type",
    "risk_level", "changed_files", "test_plan", "expected_outputs",
}

FILE_REQUIRED_FIELDS = {"path", "diff_content", "zone"}


class PatchValidator:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def validate_patch_format(self, patch_data: dict) -> tuple[bool, list[str]]:
        errors: list[str] = []
        missing = PATCH_REQUIRED_FIELDS - set(patch_data.keys())
        if missing:
            errors.append(f"Missing required fields: {sorted(missing)}")
        for idx, f in enumerate(patch_data.get("changed_files", [])):
            missing_f = FILE_REQUIRED_FIELDS - set(f.keys())
            if missing_f:
                errors.append(f"changed_files[{idx}] missing: {sorted(missing_f)}")
        if not patch_data.get("changed_files"):
            errors.append("changed_files must not be empty")
        return (len(errors) == 0, errors)

    def validate_diff_syntax(self, diff_content: str) -> tuple[bool, str]:
        if not diff_content.strip():
            return (False, "Diff content is empty")
        has_old = bool(re.search(r"^--- ", diff_content, re.MULTILINE))
        has_new = bool(re.search(r"^\+\+\+ ", diff_content, re.MULTILINE))
        has_hunk = bool(re.search(r"^@@ ", diff_content, re.MULTILINE))
        if not has_old:
            return (False, "Missing '---' header line")
        if not has_new:
            return (False, "Missing '+++' header line")
        if not has_hunk:
            return (False, "Missing '@@' hunk markers")
        return (True, "")

    def validate_risk_consistency(self, patch_data: dict) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        risk = patch_data.get("risk_level", "low")
        risk_rank = RISK_ORDER.get(risk, 0)
        zones = {f.get("zone", "") for f in patch_data.get("changed_files", [])}
        if "red" in zones and risk != "critical":
            warnings.append("Red-zone file present; risk_level must be 'critical'")
        if "yellow" in zones and risk_rank < RISK_ORDER["medium"]:
            warnings.append("Yellow-zone file present; risk_level must be >= 'medium'")
        return (len(warnings) == 0, warnings)

    def validate_file_deletion_safety(self, changed_files: list[dict]) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        for f in changed_files:
            diff = f.get("diff_content", "")
            is_delete = bool(re.search(r"^--- .+\n\+\+\+ /dev/null", diff, re.MULTILINE))
            if is_delete and f.get("zone") != "green":
                warnings.append(f"Deleting non-green-zone file: {f.get('path', '?')}")
        return (len(warnings) == 0, warnings)
