"""Local AP8/AE8 trapped-radiation dataset manifest and download helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from knowledge_base.space_radiation.paths import AP8AE8_DATA_ROOT

AP8AE8_DATASET_ID = "nasa-radbelt-aep8"
NASA_RADBELT_REPOSITORY = "https://github.com/nasa/radbelt"
NASA_RADBELT_RAW_BASE = (
    "https://raw.githubusercontent.com/nasa/radbelt/main/radbelt/extern/aep8"
)
NASA_RADBELT_LICENSE_URL = (
    "https://raw.githubusercontent.com/nasa/radbelt/main/LICENSE.txt"
)

AP8AE8_MODEL_FILES: tuple[str, ...] = (
    "ap8min.asc",
    "ap8max.asc",
    "ae8min.asc",
    "ae8max.asc",
    "trmfun.f",
    "README.md",
    "LICENSE.txt",
)

AP8AE8_MODELS: dict[str, dict[str, str]] = {
    "AP8MIN": {
        "file": "ap8min.asc",
        "particle": "proton",
        "solar_period": "min",
        "flux": "integral omnidirectional trapped proton flux",
    },
    "AP8MAX": {
        "file": "ap8max.asc",
        "particle": "proton",
        "solar_period": "max",
        "flux": "integral omnidirectional trapped proton flux",
    },
    "AE8MIN": {
        "file": "ae8min.asc",
        "particle": "electron",
        "solar_period": "min",
        "flux": "integral omnidirectional trapped electron flux",
    },
    "AE8MAX": {
        "file": "ae8max.asc",
        "particle": "electron",
        "solar_period": "max",
        "flux": "integral omnidirectional trapped electron flux",
    },
}

AP8AE8_LIMITATIONS: tuple[str, ...] = (
    "Requires magnetic coordinates such as L-shell and B/B0; altitude/inclination alone "
    "are not enough for this first RadAgent adapter.",
    "AP8/AE8 are static trapped-belt empirical models, not dynamic space-weather, SEP, "
    "or GCR models.",
    "MIN/MAX select solar-cycle map variants and must not be interpolated as a real-time "
    "space-weather forecast.",
)


@dataclass(frozen=True)
class AP8AE8Verification:
    """Result of checking the local AP8/AE8 dataset directory."""

    ok: bool
    missing_files: list[str]
    manifest: dict | None = None


def manifest_path(data_dir: Path = AP8AE8_DATA_ROOT) -> Path:
    """Return the AP8/AE8 manifest path under a data directory."""
    return data_dir / "manifest.json"


def build_ap8ae8_manifest(data_dir: Path = AP8AE8_DATA_ROOT) -> dict:
    """Build a manifest for a complete local AP8/AE8 dataset directory."""
    data_dir = Path(data_dir)
    files: dict[str, dict[str, str | int]] = {}
    for filename in AP8AE8_MODEL_FILES:
        path = data_dir / filename
        payload = path.read_bytes()
        files[filename] = {
            "path": filename,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    return {
        "dataset_id": AP8AE8_DATASET_ID,
        "version": "nasa-radbelt-main",
        "source": {
            "repository": NASA_RADBELT_REPOSITORY,
            "upstream_data_path": "radbelt/extern/aep8",
            "ccmc_model": "AE-8/AP-8 RADBELT",
        },
        "models": AP8AE8_MODELS,
        "limitations": list(AP8AE8_LIMITATIONS),
        "files": files,
    }


def write_ap8ae8_manifest(data_dir: Path = AP8AE8_DATA_ROOT) -> dict:
    """Build and write `manifest.json` for the local AP8/AE8 dataset."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_ap8ae8_manifest(data_dir)
    manifest_path(data_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_ap8ae8_manifest(data_dir: Path = AP8AE8_DATA_ROOT) -> dict | None:
    """Read the local AP8/AE8 manifest if present."""
    path = manifest_path(data_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def verify_ap8ae8_dataset(data_dir: Path = AP8AE8_DATA_ROOT) -> AP8AE8Verification:
    """Verify that all required AP8/AE8 files exist and return a manifest."""
    data_dir = Path(data_dir)
    missing = [filename for filename in AP8AE8_MODEL_FILES if not (data_dir / filename).is_file()]
    if missing:
        return AP8AE8Verification(ok=False, missing_files=missing)
    manifest = read_ap8ae8_manifest(data_dir) or build_ap8ae8_manifest(data_dir)
    return AP8AE8Verification(ok=True, missing_files=[], manifest=manifest)


def download_ap8ae8_dataset(
    data_dir: Path = AP8AE8_DATA_ROOT,
    *,
    timeout: float = 20.0,
) -> dict:
    """Download AP8/AE8 data files from NASA radbelt raw URLs and write manifest."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in AP8AE8_MODEL_FILES:
        if filename == "LICENSE.txt":
            url = NASA_RADBELT_LICENSE_URL
        else:
            url = f"{NASA_RADBELT_RAW_BASE}/{filename}"
        _download_file(url, data_dir / filename, timeout=timeout)
    return write_ap8ae8_manifest(data_dir)


def _download_file(url: str, destination: Path, *, timeout: float) -> None:
    """Download a single file with a bounded network timeout."""
    with urlopen(url, timeout=timeout) as response:
        destination.write_bytes(response.read())
