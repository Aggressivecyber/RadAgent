from __future__ import annotations

import hashlib
from pathlib import Path

from knowledge_base.space_radiation.ap8ae8 import (
    AP8AE8_DATASET_ID,
    AP8AE8_MODEL_FILES,
    build_ap8ae8_manifest,
    download_ap8ae8_dataset,
    verify_ap8ae8_dataset,
)


def _write_model_files(root: Path) -> None:
    for filename in AP8AE8_MODEL_FILES:
        (root / filename).write_text(f"sample data for {filename}\n", encoding="utf-8")


def test_build_manifest_records_required_files_hashes_and_limits(tmp_path: Path) -> None:
    _write_model_files(tmp_path)

    manifest = build_ap8ae8_manifest(tmp_path)

    assert manifest["dataset_id"] == AP8AE8_DATASET_ID
    assert manifest["source"]["repository"] == "https://github.com/nasa/radbelt"
    assert manifest["source"]["upstream_data_path"] == "radbelt/extern/aep8"
    assert manifest["models"]["AP8MIN"]["particle"] == "proton"
    assert manifest["models"]["AE8MAX"]["particle"] == "electron"
    assert "L-shell" in manifest["limitations"][0]
    assert set(manifest["files"]) == set(AP8AE8_MODEL_FILES)
    expected = hashlib.sha256((tmp_path / "ap8min.asc").read_bytes()).hexdigest()
    assert manifest["files"]["ap8min.asc"]["sha256"] == expected
    assert manifest["files"]["ap8min.asc"]["bytes"] > 0


def test_verify_dataset_reports_missing_files(tmp_path: Path) -> None:
    (tmp_path / "ap8min.asc").write_text("only one file\n", encoding="utf-8")

    result = verify_ap8ae8_dataset(tmp_path)

    assert result.ok is False
    assert "ap8max.asc" in result.missing_files
    assert result.manifest is None


def test_verify_dataset_returns_manifest_when_complete(tmp_path: Path) -> None:
    _write_model_files(tmp_path)

    result = verify_ap8ae8_dataset(tmp_path)

    assert result.ok is True
    assert result.missing_files == []
    assert result.manifest is not None
    assert result.manifest["dataset_id"] == AP8AE8_DATASET_ID


def test_download_dataset_uses_timeout_and_writes_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, str, float]] = []

    def _fake_download(url: str, destination: Path, *, timeout: float) -> None:
        calls.append((url, destination.name, timeout))
        destination.write_text(f"downloaded from {url}\n", encoding="utf-8")

    monkeypatch.setattr("knowledge_base.space_radiation.ap8ae8._download_file", _fake_download)

    manifest = download_ap8ae8_dataset(tmp_path, timeout=7.5)

    assert len(calls) == len(AP8AE8_MODEL_FILES)
    assert all(call[2] == 7.5 for call in calls)
    assert (tmp_path / "manifest.json").is_file()
    assert manifest["dataset_id"] == AP8AE8_DATASET_ID
