"""Patch application tool with zone-based file access policy enforcement."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from agent_core.validators.file_permission_validator import FilePermissionValidator

logger = logging.getLogger(__name__)


class PatchTool:
    """Apply code patches with safety checks, backups, and rollback.

    Respects file access policy (green/yellow/red zones).
    Creates .bak backups before every modification.
    """

    def __init__(self, workspace_root: str, policy_path: str = "agent_core/policies/file_access_policy.yaml") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self._validator = FilePermissionValidator(policy_path)
        self._suffix = ".bak"

    def apply_patch(self, patch_data: dict, dry_run: bool = False) -> dict[str, Any]:
        """Apply a CodePatch-shaped dict. Returns {applied, rejected, warnings, backups_created}."""
        applied, rejected, warnings, backups = [], [], [], []
        changed_files = patch_data.get("changed_files", [])
        change_type = patch_data.get("change_type", "modify")

        for entry in changed_files:
            rel = entry.get("path", "")
            content = entry.get("new_content", "")
            zone = self._validator.classify_file(rel)

            if zone == "red":
                rejected.append(rel)
                warnings.append(f"REJECT (red zone): {rel}")
                logger.warning("Patch rejected (red zone): %s", rel)
                continue

            if zone == "yellow":
                warnings.append(f"REVIEW NEEDED (yellow zone): {rel}")

            if not dry_run:
                target = self._resolve(rel)
                if target.exists():
                    backups.append(self._create_backup(rel))
                self._apply_single_file(rel, content, change_type)
            applied.append(rel)
            logger.info("Patch applied (%s zone): %s", zone, rel)

        return {"applied": applied, "rejected": rejected, "warnings": warnings, "backups_created": backups}

    def rollback(self, patch_data: dict) -> bool:
        """Restore files from .bak copies. Returns True on full success."""
        ok = True
        for entry in patch_data.get("changed_files", []):
            rel = entry.get("path", "")
            backup, target = self._resolve(rel + self._suffix), self._resolve(rel)
            if backup.exists():
                shutil.copy2(backup, target)
                backup.unlink()
                logger.info("Rolled back: %s", rel)
            else:
                logger.error("No backup for rollback: %s", rel)
                ok = False
        return ok

    def write_new_file(self, file_path: str, content: str) -> bool:
        """Write a brand-new file. Fails if file already exists."""
        abs_path = self._resolve(file_path)
        if abs_path.exists():
            logger.error("File already exists: %s", file_path)
            return False
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        logger.info("Created new file: %s", file_path)
        return True

    # -- internals --

    def _apply_single_file(self, file_path: str, content: str, change_type: str) -> bool:
        abs_path = self._resolve(file_path)
        if change_type == "delete":
            if abs_path.exists():
                abs_path.unlink()
            return True
        if change_type == "create":
            return self.write_new_file(file_path, content)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        return True

    def _create_backup(self, file_path: str) -> str:
        abs_path = self._resolve(file_path)
        backup = abs_path.with_name(abs_path.name + self._suffix)
        if abs_path.exists():
            shutil.copy2(abs_path, backup)
        return file_path + self._suffix

    def _resolve(self, rel_path: str) -> Path:
        return self.workspace_root / rel_path
