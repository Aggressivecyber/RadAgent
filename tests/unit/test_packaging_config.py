from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from knowledge_base.tcad.wechat_scraper.url_collector import collect_from_sogou
from setuptools import find_packages


def _requirement_name(requirement: str) -> str:
    name = requirement
    for sep in ("[", "<", ">", "=", "!", "~", ";"):
        name = name.split(sep, 1)[0]
    return name.strip().lower().replace("_", "-")


def test_packaging_includes_runtime_packages() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    include = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]

    packages = set(find_packages(include=include))

    assert "agent_core" in packages
    assert "agent_core.tui" in packages
    assert "knowledge_base" in packages
    assert "knowledge_base.geant4" in packages
    assert "knowledge_base.tcad" in packages
    assert "knowledge_base.tcad.wechat_scraper" in packages


def test_runtime_dependencies_match_direct_import_boundaries() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = {
        _requirement_name(requirement)
        for requirement in pyproject["project"]["dependencies"]
    }
    wechat_scraper_extra = {
        _requirement_name(requirement)
        for requirement in pyproject["project"]["optional-dependencies"]["wechat-scraper"]
    }

    assert "httpx" in dependencies
    assert "langchain-core" not in dependencies
    assert "langchain-openai" not in dependencies
    assert "jsonschema" not in dependencies
    assert "h5py" not in dependencies
    assert "pandas" not in dependencies

    assert "beautifulsoup4" not in dependencies
    assert "requests" not in dependencies
    assert {"beautifulsoup4", "requests"} <= wechat_scraper_extra


def test_wechat_discovery_reports_missing_optional_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = __import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"requests", "bs4"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="wechat-scraper"):
        collect_from_sogou("account", max_pages=1)
