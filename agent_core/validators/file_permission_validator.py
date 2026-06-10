"""File permission validator enforcing zone-based access policy."""

from fnmatch import fnmatch
from importlib.resources import files
from pathlib import Path

import yaml


class FilePermissionValidator:
    """Classifies files into green/yellow/red zones and validates patch permissions."""

    def __init__(self, policy_path: str | Path | None = None):
        raw = yaml.safe_load(_read_policy_text(policy_path))
        self._zones = {}
        for zone in ("green_zone", "yellow_zone", "red_zone"):
            self._zones[zone] = raw.get(zone, {}).get("patterns", [])
        self._default_action = raw.get("default_action", "reject")

    def classify_file(self, file_path: str) -> str:
        """Return 'green', 'yellow', or 'red' based on policy patterns."""
        for zone_key in ("red_zone", "yellow_zone", "green_zone"):
            for pattern in self._zones.get(zone_key, []):
                if fnmatch(file_path, pattern):
                    return zone_key.replace("_zone", "")
        # Files matching no pattern fall back to default
        return "red" if self._default_action == "reject" else "green"

    def validate_patch_permissions(self, changed_files: list[dict]) -> tuple[bool, list[str]]:
        """Validate a list of changed files against the access policy.

        Each dict must have a 'path' key. Returns (all_allowed, messages).
        Red-zone files cause rejection; yellow-zone files add review warnings.
        """
        all_allowed = True
        messages: list[str] = []

        for entry in changed_files:
            path = entry.get("path", "")
            zone = self.classify_file(path)

            if zone == "red":
                all_allowed = False
                messages.append(f"REJECT (red zone): {path}")
            elif zone == "yellow":
                messages.append(f"REVIEW NEEDED (yellow zone): {path}")
            else:
                messages.append(f"OK (green zone): {path}")

        return all_allowed, messages

    def can_auto_apply(self, file_path: str) -> bool:
        """Return True only for green-zone files."""
        return self.classify_file(file_path) == "green"


def _read_policy_text(policy_path: str | Path | None) -> str:
    if policy_path is not None:
        return Path(policy_path).read_text(encoding="utf-8")
    return (
        files("agent_core.policies")
        .joinpath("file_access_policy.yaml")
        .read_text(encoding="utf-8")
    )
