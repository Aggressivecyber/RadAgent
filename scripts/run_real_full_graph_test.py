#!/usr/bin/env python3
"""Run the real G4 full-graph acceptance test with the configured model API."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/real_full_graph/test_real_g4_codegen_full_graph.py",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
