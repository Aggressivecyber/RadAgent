from __future__ import annotations

import tomllib
from pathlib import Path

from agent_core.validators.file_permission_validator import FilePermissionValidator


def test_default_policy_loads_without_repo_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    validator = FilePermissionValidator()

    assert validator.classify_file("src/Detector.cc") == "green"
    assert validator.classify_file("agent_core/main.py") == "red"


def test_policy_yaml_is_declared_as_package_data() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert "policies/*.yaml" in package_data["agent_core"]
