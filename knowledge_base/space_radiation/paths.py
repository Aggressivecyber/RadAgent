"""Path helpers for local space-radiation datasets."""

from __future__ import annotations

from pathlib import Path

SPACE_RADIATION_KB_ROOT = Path(__file__).resolve().parent
SPACE_RADIATION_DATA_ROOT = SPACE_RADIATION_KB_ROOT / "data"
AP8AE8_DATA_ROOT = SPACE_RADIATION_DATA_ROOT / "ap8ae8"

