#!/usr/bin/env python3
"""Run real G4 module-agent tests with a non-mock provider."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    provider = os.environ.get("RADAGENT_MODEL_PROVIDER", "").lower()
    if provider == "mock":
        print("RADAGENT_MODEL_PROVIDER=mock is not allowed for real module tests.", file=sys.stderr)
        return 1
    os.environ["RADAGENT_MODEL_PROVIDER"] = provider or "openai_compatible"
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "tests/real_g4_modules/"])


if __name__ == "__main__":
    raise SystemExit(main())
