#!/usr/bin/env python3
"""Run the real G4 full-graph acceptance test with a non-mock provider."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    provider = os.environ.get("RADAGENT_MODEL_PROVIDER", "").lower()
    if provider == "mock":
        print(
            "RADAGENT_MODEL_PROVIDER=mock is not allowed for real full-graph tests.",
            file=sys.stderr,
        )
        return 1
    os.environ["RADAGENT_MODEL_PROVIDER"] = provider or "openai_compatible"
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
