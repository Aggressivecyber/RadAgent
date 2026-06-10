#!/usr/bin/env python3
"""Regenerate tracked review fixtures from the canonical artifact generator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from scripts.generate_complex_model_artifact import main as generate

    generate()


if __name__ == "__main__":
    main()
